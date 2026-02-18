"""
Generic website media extractor.

Scans websites for video content by detecting:
- Direct video file links (mp4, webm, etc.)
- HLS/DASH manifests (m3u8, mpd)
- Embedded video players (video tags, iframes)
- Common video platforms (embedded YouTube, Vimeo, etc.)
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from scanner.extractors.base import BaseExtractor, register_extractor
from scanner.http_client import http_client
from scanner.models import (
    MediaItem,
    MediaType,
    Platform,
    ScanRequest,
    ScanResult,
    ScanStatus,
    StreamInfo,
    StreamProtocol,
    StreamQuality,
)


@register_extractor
class GenericExtractor(BaseExtractor):
    """
    Generic extractor for websites with video content.
    
    This extractor scans HTML pages for:
    - <video> tags with src attributes
    - <source> elements within video tags
    - <iframe> embeds of video platforms
    - Direct links to video files
    - HLS/DASH manifest URLs in scripts
    - JSON-LD structured data
    """
    
    PLATFORM = Platform.WEBSITE
    URL_PATTERNS = [
        # Match any HTTP(S) URL as fallback
        re.compile(r'^https?://'),
    ]
    
    # Video file extensions
    VIDEO_EXTENSIONS = {
        '.mp4', '.m4v', '.webm', '.mkv', '.avi', '.mov',
        '.flv', '.wmv', '.ts', '.m3u8', '.mpd'
    }
    
    # Patterns to find media URLs in page content
    MEDIA_PATTERNS = [
        # HLS manifests
        re.compile(r'["\']([^"\']*\.m3u8[^"\']*)["\']'),
        re.compile(r'src\s*[=:]\s*["\']([^"\']*\.m3u8[^"\']*)["\']'),
        
        # DASH manifests
        re.compile(r'["\']([^"\']*\.mpd[^"\']*)["\']'),
        
        # Direct video files
        re.compile(r'["\']([^"\']*\.mp4[^"\']*)["\']'),
        re.compile(r'["\']([^"\']*\.webm[^"\']*)["\']'),
        
        # Common player patterns
        re.compile(r'file\s*[=:]\s*["\']([^"\']+)["\']'),
        re.compile(r'source\s*[=:]\s*["\']([^"\']+)["\']'),
        re.compile(r'videoUrl\s*[=:]\s*["\']([^"\']+)["\']'),
        re.compile(r'streamUrl\s*[=:]\s*["\']([^"\']+)["\']'),
        re.compile(r'hlsUrl\s*[=:]\s*["\']([^"\']+)["\']'),
        re.compile(r'manifestUrl\s*[=:]\s*["\']([^"\']+)["\']'),
    ]
    
    async def extract(self, request: ScanRequest) -> ScanResult:
        """Extract media from a generic website."""
        result = self._create_result(request)
        result.started_at = datetime.utcnow()
        
        visited: Set[str] = set()
        
        try:
            await self._scan_page(
                result,
                request.url,
                visited,
                depth=0,
                max_depth=request.max_depth,
                follow_links=request.follow_links,
                max_items=request.max_items
            )
            
            result.status = ScanStatus.COMPLETED
            result.total_count = len(result.items)
            
        except Exception as e:
            self.logger.error(f"Generic extraction failed: {e}", exc_info=True)
            result.status = ScanStatus.FAILED
            result.error_message = str(e)
        
        result.completed_at = datetime.utcnow()
        if result.started_at:
            result.duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
        
        return result
    
    async def _scan_page(
        self,
        result: ScanResult,
        url: str,
        visited: Set[str],
        depth: int,
        max_depth: int,
        follow_links: bool,
        max_items: int
    ) -> None:
        """Scan a single page for media content."""
        # Skip if already visited or max items reached
        if url in visited or len(result.items) >= max_items:
            return
        
        visited.add(url)
        result.pages_scanned += 1
        
        # Fetch page
        response = await http_client.get(url)
        result.requests_made += 1
        
        if not response.success:
            return
        
        html = response.text
        base_url = url
        
        # Extract page metadata
        if depth == 0:
            result.source_title = self._extract_title(html)
        
        # Find media on this page
        media_urls = self._find_media_urls(html, base_url)
        
        for media_url, media_type, metadata in media_urls:
            if len(result.items) >= max_items:
                break
            
            # Skip duplicates
            if any(item.stream_url == media_url for item in result.items):
                continue
            
            item = MediaItem(
                title=metadata.get('title', self._generate_title(media_url)),
                url=url,
                stream_url=media_url,
                platform=Platform.WEBSITE,
                media_type=media_type,
                thumbnail_url=metadata.get('thumbnail'),
                duration=metadata.get('duration'),
                extractor=self.__class__.__name__,
            )
            
            # Add stream info
            protocol = self._detect_protocol(media_url)
            item.streams.append(StreamInfo(
                url=media_url,
                quality=StreamQuality.UNKNOWN,
                protocol=protocol,
            ))
            
            result.items.append(item)
        
        # Follow links if enabled
        if follow_links and depth < max_depth:
            links = self._extract_links(html, base_url)
            for link in links:
                if len(result.items) >= max_items:
                    break
                await self._scan_page(
                    result, link, visited,
                    depth + 1, max_depth, follow_links, max_items
                )
    
    def _find_media_urls(
        self,
        html: str,
        base_url: str
    ) -> List[Tuple[str, MediaType, Dict[str, Any]]]:
        """Find all media URLs in HTML content."""
        results = []
        seen_urls = set()
        
        # 1. Find <video> tags
        video_items = self._extract_video_tags(html, base_url)
        for url, metadata in video_items:
            if url not in seen_urls:
                seen_urls.add(url)
                media_type = MediaType.LIVE if '.m3u8' in url else MediaType.VOD
                results.append((url, media_type, metadata))
        
        # 2. Find <iframe> embeds
        iframe_items = self._extract_iframes(html, base_url)
        for url, metadata in iframe_items:
            if url not in seen_urls:
                seen_urls.add(url)
                results.append((url, MediaType.VOD, metadata))
        
        # 3. Find URLs in scripts
        script_items = self._extract_from_scripts(html, base_url)
        for url, metadata in script_items:
            if url not in seen_urls:
                seen_urls.add(url)
                media_type = MediaType.LIVE if '.m3u8' in url else MediaType.VOD
                results.append((url, media_type, metadata))
        
        # 4. Find JSON-LD structured data
        jsonld_items = self._extract_json_ld(html, base_url)
        for url, metadata in jsonld_items:
            if url not in seen_urls:
                seen_urls.add(url)
                results.append((url, MediaType.VOD, metadata))
        
        return results
    
    def _extract_video_tags(
        self,
        html: str,
        base_url: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Extract media from <video> tags."""
        results = []
        
        # Find video tags
        video_pattern = re.compile(
            r'<video[^>]*>(.*?)</video>|<video[^>]*/?>',
            re.IGNORECASE | re.DOTALL
        )
        
        for match in video_pattern.finditer(html):
            video_html = match.group(0)
            metadata: Dict[str, Any] = {}
            
            # Get poster
            if poster_match := re.search(r'poster\s*=\s*["\']([^"\']+)["\']', video_html):
                metadata['thumbnail'] = urljoin(base_url, poster_match.group(1))
            
            # Get src from video tag
            if src_match := re.search(r'src\s*=\s*["\']([^"\']+)["\']', video_html):
                src = urljoin(base_url, src_match.group(1))
                if self._is_video_url(src):
                    results.append((src, metadata))
            
            # Get src from source tags
            source_pattern = re.compile(r'<source[^>]*src\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
            for source_match in source_pattern.finditer(video_html):
                src = urljoin(base_url, source_match.group(1))
                if self._is_video_url(src):
                    results.append((src, metadata.copy()))
        
        return results
    
    def _extract_iframes(
        self,
        html: str,
        base_url: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Extract embedded video iframes."""
        results = []
        
        iframe_pattern = re.compile(
            r'<iframe[^>]*src\s*=\s*["\']([^"\']+)["\'][^>]*>',
            re.IGNORECASE
        )
        
        # Known video embed domains
        video_domains = {
            'youtube.com', 'youtube-nocookie.com', 'youtu.be',
            'vimeo.com', 'player.vimeo.com',
            'dailymotion.com', 'dai.ly',
            'twitch.tv', 'player.twitch.tv',
            'facebook.com', 'fb.watch',
            'rumble.com',
        }
        
        for match in iframe_pattern.finditer(html):
            src = match.group(1)
            full_url = urljoin(base_url, src)
            parsed = urlparse(full_url)
            
            # Check if it's a known video embed
            domain = parsed.netloc.lower().replace('www.', '')
            if any(vd in domain for vd in video_domains):
                results.append((full_url, {'type': 'embed'}))
        
        return results
    
    def _extract_from_scripts(
        self,
        html: str,
        base_url: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Extract media URLs from script content."""
        results = []
        
        # Find all script content
        script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL)
        
        for script_match in script_pattern.finditer(html):
            script_content = script_match.group(1)
            
            # Apply all media patterns
            for pattern in self.MEDIA_PATTERNS:
                for url_match in pattern.finditer(script_content):
                    url = url_match.group(1)
                    
                    # Clean and validate URL
                    url = url.strip()
                    if not url or url.startswith('//'):
                        url = 'https:' + url if url.startswith('//') else url
                    
                    if self._is_video_url(url):
                        full_url = urljoin(base_url, url)
                        results.append((full_url, {}))
        
        return results
    
    def _extract_json_ld(
        self,
        html: str,
        base_url: str
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Extract media from JSON-LD structured data."""
        results = []
        
        jsonld_pattern = re.compile(
            r'<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.IGNORECASE | re.DOTALL
        )
        
        for match in jsonld_pattern.finditer(html):
            try:
                data = json.loads(match.group(1))
                
                # Handle array of items
                items = data if isinstance(data, list) else [data]
                
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    
                    item_type = item.get('@type', '')
                    
                    # VideoObject
                    if 'Video' in item_type:
                        metadata = {
                            'title': item.get('name'),
                            'description': item.get('description'),
                            'thumbnail': item.get('thumbnailUrl'),
                            'duration': self._parse_duration(item.get('duration', '')),
                        }
                        
                        if content_url := item.get('contentUrl'):
                            results.append((content_url, metadata))
                        if embed_url := item.get('embedUrl'):
                            results.append((embed_url, metadata))
            
            except json.JSONDecodeError:
                continue
        
        return results
    
    def _extract_links(self, html: str, base_url: str) -> List[str]:
        """Extract links to follow for deeper scanning."""
        links = []
        parsed_base = urlparse(base_url)
        
        # Find anchor tags
        link_pattern = re.compile(r'<a[^>]*href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
        
        for match in link_pattern.finditer(html):
            href = match.group(1)
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            
            # Only follow links to same domain
            if parsed.netloc == parsed_base.netloc:
                # Skip non-HTML resources
                if not any(parsed.path.endswith(ext) for ext in 
                          ['.jpg', '.png', '.gif', '.css', '.js', '.pdf']):
                    links.append(full_url)
        
        return links[:20]  # Limit links to follow
    
    def _extract_title(self, html: str) -> Optional[str]:
        """Extract page title."""
        # Try <title> tag
        if match := re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE):
            return match.group(1).strip()
        
        # Try og:title
        if match := re.search(r'property\s*=\s*["\']og:title["\'][^>]*content\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE):
            return match.group(1).strip()
        
        return None
    
    def _is_video_url(self, url: str) -> bool:
        """Check if URL points to a video resource."""
        if not url:
            return False
        
        parsed = urlparse(url.lower())
        path = parsed.path
        
        # Check extension
        for ext in self.VIDEO_EXTENSIONS:
            if ext in path:
                return True
        
        # Check for streaming keywords
        streaming_keywords = ['stream', 'video', 'media', 'player', 'hls', 'dash']
        if any(kw in url.lower() for kw in streaming_keywords):
            return True
        
        return False
    
    def _generate_title(self, url: str) -> str:
        """Generate a title from URL."""
        parsed = urlparse(url)
        path = parsed.path
        
        # Get filename without extension
        if '/' in path:
            filename = path.rsplit('/', 1)[-1]
        else:
            filename = path
        
        # Remove extension
        for ext in self.VIDEO_EXTENSIONS:
            if filename.endswith(ext):
                filename = filename[:-len(ext)]
                break
        
        # Clean up
        filename = filename.replace('_', ' ').replace('-', ' ').strip()
        
        return filename if filename else parsed.netloc