"""
Playlist file extractor.

Extracts media items from M3U, M3U8, and PLS playlist files.
"""

import re
from typing import List, Optional, Pattern

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
class PlaylistExtractor(BaseExtractor):
    """
    Extractor for playlist files (M3U, M3U8, PLS).
    
    Parses playlist files to extract media items. Useful for importing
    existing IPTV lists or bulk-importing streams.
    """
    
    PLATFORM = Platform.PLAYLIST
    URL_PATTERNS = [
        re.compile(r'^https?://.*\.m3u8?(\?.*)?$', re.IGNORECASE),
        re.compile(r'^https?://.*\.pls(\?.*)?$', re.IGNORECASE),
    ]
    
    async def extract(self, request: ScanRequest) -> ScanResult:
        """Extract media from playlist file."""
        result = self._create_result(request)
        result.platform = Platform.PLAYLIST
        
        try:
            # Fetch playlist content
            response = await http_client.get(request.url)
            
            if not response.success:
                result.status = ScanStatus.FAILED
                result.error_message = f"Failed to fetch playlist: {response.status_code}"
                return result
            
            content = response.text
            
            # Determine format and parse
            if '#EXTM3U' in content or request.url.lower().endswith(('.m3u', '.m3u8')):
                items = self._parse_m3u(content, request)
            elif '[playlist]' in content.lower():
                items = self._parse_pls(content, request)
            else:
                # Try M3U fallback if it looks like a list of URLs
                items = self._parse_m3u(content, request)
            
            # Add valid items
            result.items = items
            result.total_count = len(items)
            result.status = ScanStatus.COMPLETED
            
        except Exception as e:
            self.logger.error(f"Playlist extraction failed: {e}", exc_info=True)
            result.status = ScanStatus.FAILED
            result.error_message = str(e)
        
        return result

    def _parse_m3u(self, content: str, request: ScanRequest) -> List[MediaItem]:
        """Parse M3U content."""
        items = []
        lines = content.splitlines()
        
        current_item = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('#EXTINF:'):
                current_item = self._parse_extinf(line)
            elif line.startswith('#'):
                # Other directives (ignore for now)
                continue
            else:
                # URL line
                if current_item:
                    current_item.url = line
                    current_item.stream_url = line
                    
                    # Create default stream info
                    current_item.streams = [StreamInfo(
                        url=line,
                        protocol=self._detect_protocol(line),
                        quality=StreamQuality.UNKNOWN
                    )]
                    
                    # Refine media type based on duration
                    if current_item.duration == -1:
                         current_item.media_type = MediaType.LIVE
                         current_item.is_live = True
                    elif current_item.duration and current_item.duration > 0:
                         current_item.media_type = MediaType.VOD
                    
                    items.append(current_item)
                    current_item = None
                
                # Check limit
                if len(items) >= request.max_items:
                    break
        
        return items

    def _parse_extinf(self, line: str) -> MediaItem:
        """Parse EXTINF line into MediaItem."""
        # Format: #EXTINF:duration attributes,Title
        
        # Split attributes and title
        parts = line[8:].split(',', 1)
        meta_part = parts[0]
        title = parts[1].strip() if len(parts) > 1 else "Unknown"
        
        item = MediaItem(
            title=title,
            platform=Platform.UNKNOWN, # Will rely on stream URL detection or default
            extractor=self.__class__.__name__
        )
        
        # Parse duration
        # Example: #EXTINF:-1 ...
        duration_match = re.match(r'^(-?\d+)', meta_part)
        if duration_match:
            duration = int(duration_match.group(1))
            if duration == -1:
                item.is_live = True
                item.media_type = MediaType.LIVE
            else:
                item.duration = duration
                item.media_type = MediaType.VOD
        
        # Parse standard attributes
        # tvg-id="cnn" tvg-name="CNN" tvg-logo="..." group-title="News"
        attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', meta_part))
        
        if 'tvg-id' in attrs:
            item.external_id = attrs['tvg-id']
        if 'tvg-logo' in attrs:
            item.thumbnail_url = attrs['tvg-logo']
            item.channel_logo = attrs['tvg-logo']
        if 'group-title' in attrs:
            item.category = attrs['group-title']
        if 'tvg-name' in attrs:
            # Prefer tvg-name as official channel name
            item.channel_name = attrs['tvg-name'] 
        
        return item

    def _parse_pls(self, content: str, request: ScanRequest) -> List[MediaItem]:
        """Parse PLS content."""
        # PLS format is INI-style
        import configparser
        items = []
        
        parser = configparser.ConfigParser(strict=False)
        try:
            parser.read_string(content)
            if 'playlist' in parser:
                section = parser['playlist']
                count = int(section.get('NumberOfEntries', 0))
                
                for i in range(1, count + 1):
                    if len(items) >= request.max_items:
                        break
                        
                    url = section.get(f'File{i}')
                    if not url:
                        continue
                        
                    title = section.get(f'Title{i}', f'Stream {i}')
                    length = section.get(f'Length{i}', '0')
                    
                    item = MediaItem(
                        title=title,
                        url=url,
                        stream_url=url,
                        platform=Platform.UNKNOWN,
                        extractor=self.__class__.__name__
                    )
                    
                    try:
                        duration = int(length)
                        if duration == -1:
                            item.is_live = True
                            item.media_type = MediaType.LIVE
                        elif duration > 0:
                            item.duration = duration
                            item.media_type = MediaType.VOD
                    except ValueError:
                        pass
                    
                    item.streams = [StreamInfo(
                        url=url,
                        protocol=self._detect_protocol(url)
                    )]
                    
                    items.append(item)
                    
        except Exception as e:
            self.logger.warning(f"Error parsing PLS: {e}")
            
        return items
