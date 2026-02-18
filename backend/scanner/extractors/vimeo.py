"""
Vimeo media extractor.

Extracts videos from Vimeo channels, users, and direct video links.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

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
class VimeoExtractor(BaseExtractor):
    """
    Extractor for Vimeo content.
    
    Supports:
    - Individual videos
    - User profiles
    - Channels
    - Showcases
    """
    
    PLATFORM = Platform.VIMEO
    URL_PATTERNS = [
        # Video URLs
        re.compile(r'(?:https?://)?(?:www\.)?vimeo\.com/(?P<id>\d+)'),
        re.compile(r'(?:https?://)?player\.vimeo\.com/video/(?P<id>\d+)'),
        
        # User URLs
        re.compile(r'(?:https?://)?(?:www\.)?vimeo\.com/(?P<user>[^/\d][^/]+)/?$'),
        re.compile(r'(?:https?://)?(?:www\.)?vimeo\.com/(?P<user>[^/]+)/videos'),
        
        # Channel URLs
        re.compile(r'(?:https?://)?(?:www\.)?vimeo\.com/channels/(?P<channel>[^/]+)'),
        
        # Showcase URLs
        re.compile(r'(?:https?://)?(?:www\.)?vimeo\.com/showcase/(?P<showcase>\d+)'),
    ]
    
    API_URL = "https://api.vimeo.com"
    PLAYER_URL = "https://player.vimeo.com/video"
    
    async def extract(self, request: ScanRequest) -> ScanResult:
        """Extract Vimeo content."""
        result = self._create_result(request)
        result.started_at = datetime.utcnow()
        
        try:
            url = request.url
            
            # Determine URL type
            if match := re.search(r'vimeo\.com/(\d+)', url):
                # Single video
                video_id = match.group(1)
                item = await self._extract_video(video_id)
                if item:
                    result.items.append(item)
                    
            elif match := re.search(r'vimeo\.com/channels/([^/?]+)', url):
                # Channel
                channel = match.group(1)
                await self._extract_channel(result, channel, request)
                
            elif match := re.search(r'vimeo\.com/([^/\d][^/?]+)', url):
                # User profile
                user = match.group(1)
                if user not in ['channels', 'showcase', 'watch', 'features']:
                    await self._extract_user(result, user, request)
            
            result.status = ScanStatus.COMPLETED
            result.total_count = len(result.items)
            
        except Exception as e:
            self.logger.error(f"Vimeo extraction failed: {e}", exc_info=True)
            result.status = ScanStatus.FAILED
            result.error_message = str(e)
        
        result.completed_at = datetime.utcnow()
        if result.started_at:
            result.duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
        
        return result
    
    async def _extract_video(self, video_id: str) -> Optional[MediaItem]:
        """Extract a single video."""
        try:
            # Fetch player page to get config
            player_url = f"{self.PLAYER_URL}/{video_id}"
            response = await http_client.get(player_url)
            
            if not response.success:
                return None
            
            # Extract config JSON
            config = self._extract_player_config(response.text)
            if not config:
                return None
            
            return self._parse_video_config(video_id, config)
            
        except Exception as e:
            self.logger.error(f"Failed to extract video {video_id}: {e}")
            return None
    
    def _extract_player_config(self, html: str) -> Optional[Dict]:
        """Extract player config from embedded page."""
        # Look for config object
        patterns = [
            r'window\.playerConfig\s*=\s*({.+?});',
            r'"config"\s*:\s*({.+?})\s*,\s*"player"',
            r'config\s*=\s*({.+?});',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, html, re.DOTALL):
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        # Try finding in script tags
        script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
        for script_match in script_pattern.finditer(html):
            content = script_match.group(1)
            if 'cdn_url' in content or 'progressive' in content:
                # Try to extract JSON
                json_match = re.search(r'({[^{}]*"cdn_url"[^{}]*})', content)
                if json_match:
                    try:
                        return {'request': {'files': json.loads(json_match.group(1))}}
                    except json.JSONDecodeError:
                        continue
        
        return None
    
    def _parse_video_config(self, video_id: str, config: Dict) -> Optional[MediaItem]:
        """Parse video data from config."""
        video_data = config.get('video', {})
        request_data = config.get('request', {})
        
        item = MediaItem(
            title=video_data.get('title', f'Vimeo Video {video_id}'),
            url=f"https://vimeo.com/{video_id}",
            external_id=video_id,
            platform=Platform.VIMEO,
            media_type=MediaType.VOD,
            extractor=self.__class__.__name__,
        )
        
        # Duration
        if duration := video_data.get('duration'):
            item.duration = int(duration)
        
        # Thumbnail
        if thumbs := video_data.get('thumbs'):
            # Get best quality
            for size in ['1280', '960', '640', '480', 'base']:
                if size in thumbs:
                    item.thumbnail_url = thumbs[size]
                    break
        
        # Owner/channel
        if owner := video_data.get('owner'):
            item.channel_name = owner.get('name')
            item.channel_id = str(owner.get('id', ''))
            item.channel_url = owner.get('url')
            item.channel_logo = owner.get('img')
        
        # Privacy
        privacy = video_data.get('privacy')
        
        # Extract streams
        files = request_data.get('files', {})
        
        # HLS
        if hls := files.get('hls', {}).get('cdns', {}):
            for cdn_name, cdn_data in hls.items():
                if url := cdn_data.get('url'):
                    item.streams.append(StreamInfo(
                        url=url,
                        quality=StreamQuality.UNKNOWN,
                        protocol=StreamProtocol.HLS,
                    ))
                    if not item.stream_url:
                        item.stream_url = url
                    break
        
        # DASH
        if dash := files.get('dash', {}).get('cdns', {}):
            for cdn_name, cdn_data in dash.items():
                if url := cdn_data.get('url'):
                    item.streams.append(StreamInfo(
                        url=url,
                        quality=StreamQuality.UNKNOWN,
                        protocol=StreamProtocol.DASH,
                    ))
                    break
        
        # Progressive (direct)
        if progressive := files.get('progressive', []):
            for prog in sorted(progressive, key=lambda x: x.get('height', 0), reverse=True):
                url = prog.get('url')
                if url:
                    height = prog.get('height')
                    item.streams.append(StreamInfo(
                        url=url,
                        quality=self._detect_quality(height),
                        protocol=StreamProtocol.PROGRESSIVE,
                        height=height,
                        width=prog.get('width'),
                        bitrate=prog.get('bitrate'),
                        fps=prog.get('fps'),
                    ))
                    if not item.stream_url:
                        item.stream_url = url
        
        return item
    
    async def _extract_user(
        self,
        result: ScanResult,
        username: str,
        request: ScanRequest
    ) -> None:
        """Extract videos from a user profile."""
        try:
            url = f"https://vimeo.com/{username}/videos"
            response = await http_client.get(url)
            
            if not response.success:
                result.status = ScanStatus.FAILED
                result.error_message = "Failed to fetch user page"
                return
            
            # Extract video IDs from page
            video_ids = re.findall(r'data-clip-id="(\d+)"', response.text)
            video_ids += re.findall(r'"/(\d+)"[^>]*class="[^"]*iris_video', response.text)
            
            # Deduplicate
            video_ids = list(dict.fromkeys(video_ids))
            
            # Extract user info
            result.source_channel = username
            if title_match := re.search(r'<title>([^<]+)</title>', response.text):
                result.source_title = title_match.group(1).strip()
            
            # Extract each video
            for video_id in video_ids[:request.max_items]:
                item = await self._extract_video(video_id)
                if item:
                    result.items.append(item)
            
        except Exception as e:
            self.logger.error(f"User extraction failed: {e}")
            result.status = ScanStatus.PARTIAL
            result.error_message = str(e)
    
    async def _extract_channel(
        self,
        result: ScanResult,
        channel: str,
        request: ScanRequest
    ) -> None:
        """Extract videos from a channel."""
        try:
            url = f"https://vimeo.com/channels/{channel}/videos"
            response = await http_client.get(url)
            
            if not response.success:
                result.status = ScanStatus.FAILED
                result.error_message = "Failed to fetch channel"
                return
            
            # Extract video IDs
            video_ids = re.findall(r'data-clip-id="(\d+)"', response.text)
            video_ids += re.findall(r'"/(\d+)"', response.text)
            video_ids = list(dict.fromkeys(video_ids))
            
            result.source_channel = channel
            
            # Extract each video
            for video_id in video_ids[:request.max_items]:
                if video_id.isdigit() and len(video_id) > 5:
                    item = await self._extract_video(video_id)
                    if item:
                        result.items.append(item)
            
        except Exception as e:
            self.logger.error(f"Channel extraction failed: {e}")
            result.status = ScanStatus.PARTIAL
            result.error_message = str(e)