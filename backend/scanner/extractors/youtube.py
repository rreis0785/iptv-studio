"""
YouTube media extractor.

Extracts videos, playlists, channels, and live streams from YouTube.
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

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
class YouTubeExtractor(BaseExtractor):
    """
    Extractor for YouTube content.
    
    Supports:
    - Individual videos
    - Playlists
    - Channels (videos, live streams)
    - Shorts
    - Live streams
    """
    
    PLATFORM = Platform.YOUTUBE
    URL_PATTERNS = [
        # Standard video URLs
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=(?P<id>[\w-]+)'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/v/(?P<id>[\w-]+)'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/embed/(?P<id>[\w-]+)'),
        re.compile(r'(?:https?://)?youtu\.be/(?P<id>[\w-]+)'),
        
        # Shorts
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/shorts/(?P<id>[\w-]+)'),
        
        # Live streams
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/live/(?P<id>[\w-]+)'),
        
        # Playlists
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/playlist\?list=(?P<playlist_id>[\w-]+)'),
        
        # Channels
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/channel/(?P<channel_id>[\w-]+)'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/c/(?P<channel_name>[\w-]+)'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/@(?P<handle>[\w-]+)'),
        re.compile(r'(?:https?://)?(?:www\.)?youtube\.com/user/(?P<username>[\w-]+)'),
    ]
    
    # YouTube API endpoints
    INNERTUBE_API = "https://www.youtube.com/youtubei/v1"
    INNERTUBE_CLIENT = {
        "clientName": "WEB",
        "clientVersion": "2.20231219.04.00",
    }
    
    async def extract(self, request: ScanRequest) -> ScanResult:
        """Extract YouTube content."""
        result = self._create_result(request)
        result.started_at = datetime.utcnow()
        
        try:
            # Determine URL type and extract accordingly
            url = request.url
            
            if match := re.search(r'[?&]list=([^&]+)', url):
                # Playlist
                playlist_id = match.group(1)
                await self._extract_playlist(result, playlist_id, request)
            elif match := re.search(r'(?:channel/|c/|@|user/)([^/?]+)', url):
                # Channel
                await self._extract_channel(result, url, request)
            else:
                # Single video
                video_id = self._extract_video_id(url)
                if video_id:
                    item = await self._extract_video(video_id)
                    if item:
                        result.items.append(item)
            
            result.status = ScanStatus.COMPLETED
            result.total_count = len(result.items)
            
        except Exception as e:
            self.logger.error(f"YouTube extraction failed: {e}", exc_info=True)
            result.status = ScanStatus.FAILED
            result.error_message = str(e)
        
        result.completed_at = datetime.utcnow()
        if result.started_at:
            result.duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
        
        return result
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from URL."""
        # Try query parameter
        parsed = urlparse(url)
        if parsed.query:
            params = parse_qs(parsed.query)
            if 'v' in params:
                return params['v'][0]
        
        # Try path patterns
        patterns = [
            r'(?:v|embed|shorts|live)/([^/?]+)',
            r'youtu\.be/([^/?]+)',
        ]
        for pattern in patterns:
            if match := re.search(pattern, url):
                return match.group(1)
        
        return None
    
    async def _extract_video(self, video_id: str) -> Optional[MediaItem]:
        """Extract a single video."""
        try:
            # Fetch video page
            url = f"https://www.youtube.com/watch?v={video_id}"
            response = await http_client.get(url)
            
            if not response.success:
                return None
            
            # Extract initial player response
            player_response = self._extract_player_response(response.text)
            if not player_response:
                return None
            
            return self._parse_video_data(video_id, player_response)
            
        except Exception as e:
            self.logger.error(f"Failed to extract video {video_id}: {e}")
            return None
    
    def _extract_player_response(self, html: str) -> Optional[Dict]:
        """Extract player response JSON from page HTML."""
        patterns = [
            r'var ytInitialPlayerResponse\s*=\s*({.+?});',
            r'ytInitialPlayerResponse\s*=\s*({.+?});',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, html, re.DOTALL):
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _parse_video_data(
        self,
        video_id: str,
        player_response: Dict
    ) -> Optional[MediaItem]:
        """Parse video data from player response."""
        video_details = player_response.get('videoDetails', {})
        streaming_data = player_response.get('streamingData', {})
        
        if not video_details:
            return None
        
        # Basic info
        item = MediaItem(
            title=video_details.get('title', ''),
            description=video_details.get('shortDescription'),
            url=f"https://www.youtube.com/watch?v={video_id}",
            external_id=video_id,
            platform=Platform.YOUTUBE,
            extractor=self.__class__.__name__,
        )
        
        # Media type
        if video_details.get('isLive'):
            item.media_type = MediaType.LIVE
            item.is_live = True
        elif video_details.get('isUpcoming'):
            item.media_type = MediaType.LIVE
            item.is_upcoming = True
        else:
            item.media_type = MediaType.VOD
        
        # Duration
        if length := video_details.get('lengthSeconds'):
            item.duration = int(length)
        
        # Thumbnails
        thumbnails = video_details.get('thumbnail', {}).get('thumbnails', [])
        if thumbnails:
            # Get highest quality thumbnail
            best_thumb = max(thumbnails, key=lambda t: t.get('width', 0))
            item.thumbnail_url = best_thumb.get('url')
        
        # Channel info
        item.channel_name = video_details.get('author')
        item.channel_id = video_details.get('channelId')
        if item.channel_id:
            item.channel_url = f"https://www.youtube.com/channel/{item.channel_id}"
        
        # View count
        if views := video_details.get('viewCount'):
            item.view_count = int(views)
        
        # Age restriction
        item.is_age_restricted = video_details.get('isAgeRestricted', False)
        
        # Keywords/tags
        item.tags = video_details.get('keywords', [])
        
        # Extract streams
        item.streams = self._extract_streams(streaming_data)
        
        # Set best stream URL
        if item.streams:
            best = item.best_stream
            if best:
                item.stream_url = best.url
        
        # HLS manifest for live streams
        if item.is_live and 'hlsManifestUrl' in streaming_data:
            item.stream_url = streaming_data['hlsManifestUrl']
            item.streams.insert(0, StreamInfo(
                url=streaming_data['hlsManifestUrl'],
                quality=StreamQuality.UNKNOWN,
                protocol=StreamProtocol.HLS,
            ))
        
        return item
    
    def _extract_streams(self, streaming_data: Dict) -> List[StreamInfo]:
        """Extract available streams from streaming data."""
        streams = []
        
        # Adaptive formats (separate video/audio)
        for fmt in streaming_data.get('adaptiveFormats', []):
            stream = self._parse_format(fmt)
            if stream:
                streams.append(stream)
        
        # Combined formats
        for fmt in streaming_data.get('formats', []):
            stream = self._parse_format(fmt)
            if stream:
                streams.append(stream)
        
        return streams
    
    def _parse_format(self, fmt: Dict) -> Optional[StreamInfo]:
        """Parse a single format entry."""
        url = fmt.get('url')
        if not url:
            # Check for cipher
            if 'signatureCipher' in fmt:
                # Would need to decrypt - skip for now
                return None
            return None
        
        # Determine quality
        height = fmt.get('height')
        quality_label = fmt.get('qualityLabel')
        quality = self._detect_quality(height, quality_label)
        
        # Determine protocol
        protocol = self._detect_protocol(url)
        
        return StreamInfo(
            url=url,
            quality=quality,
            protocol=protocol,
            width=fmt.get('width'),
            height=height,
            bitrate=fmt.get('bitrate'),
            fps=fmt.get('fps'),
            video_codec=fmt.get('codecs', '').split(',')[0] if fmt.get('codecs') else None,
            audio_codec=fmt.get('audioCodec'),
        )
    
    async def _extract_playlist(
        self,
        result: ScanResult,
        playlist_id: str,
        request: ScanRequest
    ) -> None:
        """Extract videos from a playlist."""
        try:
            url = f"https://www.youtube.com/playlist?list={playlist_id}"
            response = await http_client.get(url)
            
            if not response.success:
                result.status = ScanStatus.FAILED
                result.error_message = "Failed to fetch playlist"
                return
            
            # Extract initial data
            initial_data = self._extract_initial_data(response.text)
            if not initial_data:
                result.status = ScanStatus.FAILED
                result.error_message = "Failed to parse playlist data"
                return
            
            # Parse playlist info
            playlist_data = self._find_playlist_data(initial_data)
            if playlist_data:
                result.source_title = playlist_data.get('title')
                
                # Extract video items
                videos = playlist_data.get('contents', [])
                for video in videos[:request.max_items]:
                    item = self._parse_playlist_video(video)
                    if item:
                        result.items.append(item)
            
            result.total_count = len(result.items)
            
        except Exception as e:
            self.logger.error(f"Playlist extraction failed: {e}")
            result.status = ScanStatus.PARTIAL
            result.error_message = str(e)
    
    def _extract_initial_data(self, html: str) -> Optional[Dict]:
        """Extract ytInitialData from page HTML."""
        patterns = [
            r'var ytInitialData\s*=\s*({.+?});',
            r'ytInitialData\s*=\s*({.+?});',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, html, re.DOTALL):
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
        
        return None
    
    def _find_playlist_data(self, initial_data: Dict) -> Optional[Dict]:
        """Find playlist contents in initial data."""
        try:
            contents = initial_data.get('contents', {})
            two_col = contents.get('twoColumnBrowseResultsRenderer', {})
            tabs = two_col.get('tabs', [])
            
            for tab in tabs:
                tab_renderer = tab.get('tabRenderer', {})
                content = tab_renderer.get('content', {})
                section_list = content.get('sectionListRenderer', {})
                sections = section_list.get('contents', [])
                
                for section in sections:
                    item_section = section.get('itemSectionRenderer', {})
                    section_contents = item_section.get('contents', [])
                    
                    for content_item in section_contents:
                        playlist_renderer = content_item.get('playlistVideoListRenderer', {})
                        if playlist_renderer:
                            return {
                                'title': initial_data.get('metadata', {}).get(
                                    'playlistMetadataRenderer', {}
                                ).get('title'),
                                'contents': playlist_renderer.get('contents', [])
                            }
            
        except Exception as e:
            self.logger.debug(f"Error finding playlist data: {e}")
        
        return None
    
    def _parse_playlist_video(self, video_data: Dict) -> Optional[MediaItem]:
        """Parse a video entry from playlist."""
        renderer = video_data.get('playlistVideoRenderer', {})
        if not renderer:
            return None
        
        video_id = renderer.get('videoId')
        if not video_id:
            return None
        
        item = MediaItem(
            title=renderer.get('title', {}).get('runs', [{}])[0].get('text', ''),
            url=f"https://www.youtube.com/watch?v={video_id}",
            external_id=video_id,
            platform=Platform.YOUTUBE,
            media_type=MediaType.VOD,
            extractor=self.__class__.__name__,
        )
        
        # Duration
        if length := renderer.get('lengthSeconds'):
            item.duration = int(length)
        
        # Thumbnail
        thumbnails = renderer.get('thumbnail', {}).get('thumbnails', [])
        if thumbnails:
            item.thumbnail_url = thumbnails[-1].get('url')
        
        # Channel
        short_by = renderer.get('shortBylineText', {})
        runs = short_by.get('runs', [])
        if runs:
            item.channel_name = runs[0].get('text')
            nav = runs[0].get('navigationEndpoint', {})
            browse = nav.get('browseEndpoint', {})
            item.channel_id = browse.get('browseId')
        
        return item
    
    async def _extract_channel(
        self,
        result: ScanResult,
        url: str,
        request: ScanRequest
    ) -> None:
        """Extract videos from a channel."""
        try:
            # Fetch channel page (videos tab)
            if '/videos' not in url:
                url = url.rstrip('/') + '/videos'
            
            response = await http_client.get(url)
            
            if not response.success:
                result.status = ScanStatus.FAILED
                result.error_message = "Failed to fetch channel"
                return
            
            # Extract initial data
            initial_data = self._extract_initial_data(response.text)
            if not initial_data:
                result.status = ScanStatus.FAILED
                result.error_message = "Failed to parse channel data"
                return
            
            # Parse channel info
            metadata = initial_data.get('metadata', {}).get('channelMetadataRenderer', {})
            result.source_title = metadata.get('title')
            result.source_channel = metadata.get('title')
            result.source_thumbnail = metadata.get('avatar', {}).get('thumbnails', [{}])[-1].get('url')
            
            # Extract videos
            videos = self._find_channel_videos(initial_data)
            for video in videos[:request.max_items]:
                item = self._parse_channel_video(video)
                if item:
                    item.channel_name = result.source_channel
                    result.items.append(item)
            
            result.total_count = len(result.items)
            
        except Exception as e:
            self.logger.error(f"Channel extraction failed: {e}")
            result.status = ScanStatus.PARTIAL
            result.error_message = str(e)
    
    def _find_channel_videos(self, initial_data: Dict) -> List[Dict]:
        """Find video list in channel data."""
        videos = []
        
        try:
            contents = initial_data.get('contents', {})
            two_col = contents.get('twoColumnBrowseResultsRenderer', {})
            tabs = two_col.get('tabs', [])
            
            for tab in tabs:
                tab_renderer = tab.get('tabRenderer', {})
                content = tab_renderer.get('content', {})
                
                # Rich grid (newer layout)
                rich_grid = content.get('richGridRenderer', {})
                for item in rich_grid.get('contents', []):
                    rich_item = item.get('richItemRenderer', {})
                    video = rich_item.get('content', {}).get('videoRenderer', {})
                    if video:
                        videos.append(video)
                
                # Section list (older layout)
                section_list = content.get('sectionListRenderer', {})
                for section in section_list.get('contents', []):
                    item_section = section.get('itemSectionRenderer', {})
                    grid = item_section.get('contents', [{}])[0].get('gridRenderer', {})
                    for item in grid.get('items', []):
                        video = item.get('gridVideoRenderer', {})
                        if video:
                            videos.append(video)
        
        except Exception as e:
            self.logger.debug(f"Error finding channel videos: {e}")
        
        return videos
    
    def _parse_channel_video(self, video_data: Dict) -> Optional[MediaItem]:
        """Parse a video entry from channel."""
        video_id = video_data.get('videoId')
        if not video_id:
            return None
        
        title_runs = video_data.get('title', {}).get('runs', [])
        title = title_runs[0].get('text', '') if title_runs else ''
        
        item = MediaItem(
            title=title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            external_id=video_id,
            platform=Platform.YOUTUBE,
            media_type=MediaType.VOD,
            extractor=self.__class__.__name__,
        )
        
        # Check if live
        badges = video_data.get('badges', [])
        for badge in badges:
            style = badge.get('metadataBadgeRenderer', {}).get('style', '')
            if 'LIVE' in style:
                item.is_live = True
                item.media_type = MediaType.LIVE
        
        # Duration
        if length := video_data.get('lengthText', {}).get('simpleText'):
            item.duration = self._parse_duration(length)
        
        # Thumbnail
        thumbnails = video_data.get('thumbnail', {}).get('thumbnails', [])
        if thumbnails:
            item.thumbnail_url = thumbnails[-1].get('url')
        
        # View count
        if views := video_data.get('viewCountText', {}).get('simpleText'):
            # Parse "1,234 views"
            views_match = re.search(r'[\d,]+', views.replace(',', ''))
            if views_match:
                try:
                    item.view_count = int(views_match.group())
                except ValueError:
                    pass
        
        return item