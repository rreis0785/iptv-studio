"""
Twitch media extractor.

Extracts live streams, VODs, and clips from Twitch.
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
class TwitchExtractor(BaseExtractor):
    """
    Extractor for Twitch content.
    
    Supports:
    - Live streams
    - VODs (past broadcasts)
    - Clips
    - Channels
    """
    
    PLATFORM = Platform.TWITCH
    URL_PATTERNS = [
        # Channel URLs
        re.compile(r'(?:https?://)?(?:www\.)?twitch\.tv/(?P<channel>[^/?]+)/?$'),
        re.compile(r'(?:https?://)?(?:www\.)?twitch\.tv/(?P<channel>[^/?]+)/videos'),
        
        # VOD URLs
        re.compile(r'(?:https?://)?(?:www\.)?twitch\.tv/videos/(?P<vod_id>\d+)'),
        
        # Clip URLs
        re.compile(r'(?:https?://)?(?:www\.)?twitch\.tv/[^/]+/clip/(?P<clip_id>[^/?]+)'),
        re.compile(r'(?:https?://)?clips\.twitch\.tv/(?P<clip_id>[^/?]+)'),
    ]
    
    GQL_URL = "https://gql.twitch.tv/gql"
    CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"  # Public client ID
    
    async def extract(self, request: ScanRequest) -> ScanResult:
        """Extract Twitch content."""
        result = self._create_result(request)
        result.started_at = datetime.utcnow()
        
        try:
            url = request.url
            
            # Determine URL type
            if match := re.search(r'/videos/(\d+)', url):
                # Single VOD
                vod_id = match.group(1)
                item = await self._extract_vod(vod_id)
                if item:
                    result.items.append(item)
                    
            elif match := re.search(r'/clip/([^/?]+)|clips\.twitch\.tv/([^/?]+)', url):
                # Single clip
                clip_id = match.group(1) or match.group(2)
                item = await self._extract_clip(clip_id)
                if item:
                    result.items.append(item)
                    
            else:
                # Channel
                channel_match = re.search(r'twitch\.tv/([^/?]+)', url)
                if channel_match:
                    channel = channel_match.group(1)
                    await self._extract_channel(result, channel, request)
            
            result.status = ScanStatus.COMPLETED
            result.total_count = len(result.items)
            
        except Exception as e:
            self.logger.error(f"Twitch extraction failed: {e}", exc_info=True)
            result.status = ScanStatus.FAILED
            result.error_message = str(e)
        
        result.completed_at = datetime.utcnow()
        if result.started_at:
            result.duration_ms = int(
                (result.completed_at - result.started_at).total_seconds() * 1000
            )
        
        return result
    
    async def _gql_request(self, operations: List[Dict]) -> Optional[List[Dict]]:
        """Make a GraphQL request to Twitch."""
        headers = {
            'Client-ID': self.CLIENT_ID,
            'Content-Type': 'application/json',
        }
        
        response = await http_client.post(
            self.GQL_URL,
            json=operations,
            headers=headers
        )
        
        if response.success:
            try:
                return json.loads(response.text)
            except json.JSONDecodeError:
                return None
        return None
    
    async def _extract_channel(
        self,
        result: ScanResult,
        channel: str,
        request: ScanRequest
    ) -> None:
        """Extract content from a channel."""
        # Get channel info and live status
        operations = [
            {
                "operationName": "ChannelShell",
                "variables": {"login": channel},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "580ab410bcd0c1ad194224957ae2241e5d252b2c5173d8e0cce9d32d5bb14efe"
                    }
                }
            }
        ]
        
        data = await self._gql_request(operations)
        if not data or not data[0].get('data'):
            result.status = ScanStatus.FAILED
            result.error_message = "Failed to fetch channel data"
            return
        
        channel_data = data[0]['data'].get('userOrError', {})
        if channel_data.get('__typename') == 'UserDoesNotExist':
            result.status = ScanStatus.FAILED
            result.error_message = "Channel not found"
            return
        
        result.source_title = channel_data.get('displayName', channel)
        result.source_channel = channel
        
        # Get profile image
        if profile_url := channel_data.get('profileImageURL'):
            result.source_thumbnail = profile_url
        
        # Check if live
        stream = channel_data.get('stream')
        if stream:
            item = await self._parse_live_stream(channel, channel_data, stream)
            if item:
                result.items.append(item)
        
        # Get VODs if requested
        if request.include_vod:
            vods = await self._get_channel_vods(channel, request.max_items)
            result.items.extend(vods)
        
        result.total_count = len(result.items)
    
    async def _parse_live_stream(
        self,
        channel: str,
        channel_data: Dict,
        stream_data: Dict
    ) -> Optional[MediaItem]:
        """Parse live stream data."""
        item = MediaItem(
            title=stream_data.get('title', f"{channel} Live"),
            url=f"https://twitch.tv/{channel}",
            external_id=stream_data.get('id'),
            platform=Platform.TWITCH,
            media_type=MediaType.LIVE,
            is_live=True,
            extractor=self.__class__.__name__,
        )
        
        # Channel info
        item.channel_name = channel_data.get('displayName', channel)
        item.channel_id = channel_data.get('id')
        item.channel_url = f"https://twitch.tv/{channel}"
        item.channel_logo = channel_data.get('profileImageURL')
        
        # Stream info
        item.viewer_count = stream_data.get('viewersCount')
        
        # Category/game
        if game := stream_data.get('game'):
            item.category = game.get('name')
        
        # Thumbnail
        if preview := stream_data.get('previewImageURL'):
            # Replace size placeholder
            item.thumbnail_url = preview.replace('{width}', '1280').replace('{height}', '720')
        
        # Get stream URL
        stream_url = await self._get_stream_url(channel)
        if stream_url:
            item.stream_url = stream_url
            item.streams.append(StreamInfo(
                url=stream_url,
                quality=StreamQuality.UNKNOWN,
                protocol=StreamProtocol.HLS,
            ))
        
        return item
    
    async def _get_stream_url(self, channel: str) -> Optional[str]:
        """Get HLS stream URL for a channel."""
        # Use playback access token
        operations = [
            {
                "operationName": "PlaybackAccessToken",
                "variables": {
                    "isLive": True,
                    "login": channel,
                    "isVod": False,
                    "vodID": "",
                    "playerType": "embed"
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "0828119ded1c13477966434e15800ff57ddacf13ba1911c129dc2200705b0712"
                    }
                }
            }
        ]
        
        data = await self._gql_request(operations)
        if not data or not data[0].get('data'):
            return None
        
        token_data = data[0]['data'].get('streamPlaybackAccessToken')
        if not token_data:
            return None
        
        # Build HLS URL
        token = token_data.get('value', '')
        sig = token_data.get('signature', '')
        
        return (
            f"https://usher.ttvnw.net/api/channel/hls/{channel}.m3u8"
            f"?token={token}&sig={sig}"
            f"&allow_source=true&allow_audio_only=true"
        )
    
    async def _extract_vod(self, vod_id: str) -> Optional[MediaItem]:
        """Extract a single VOD."""
        operations = [
            {
                "operationName": "VideoMetadata",
                "variables": {"channelLogin": "", "videoID": vod_id},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "49b5b8f268cdeb259d75b58dcb0c1a748e3b575571a14c1a48c82d27f3c10c9c"
                    }
                }
            }
        ]
        
        data = await self._gql_request(operations)
        if not data or not data[0].get('data'):
            return None
        
        video = data[0]['data'].get('video')
        if not video:
            return None
        
        item = MediaItem(
            title=video.get('title', ''),
            description=video.get('description'),
            url=f"https://twitch.tv/videos/{vod_id}",
            external_id=vod_id,
            platform=Platform.TWITCH,
            media_type=MediaType.VOD,
            extractor=self.__class__.__name__,
        )
        
        # Duration
        if length := video.get('lengthSeconds'):
            item.duration = int(length)
        
        # Thumbnail
        if preview := video.get('previewThumbnailURL'):
            item.thumbnail_url = preview.replace('%{width}', '1280').replace('%{height}', '720')
        
        # Channel
        if owner := video.get('owner'):
            item.channel_name = owner.get('displayName')
            item.channel_id = owner.get('id')
            item.channel_url = f"https://twitch.tv/{owner.get('login', '')}"
            item.channel_logo = owner.get('profileImageURL')
        
        # View count
        item.view_count = video.get('viewCount')
        
        # Upload date
        if created := video.get('createdAt'):
            try:
                item.upload_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
            except ValueError:
                pass
        
        # Game/category
        if game := video.get('game'):
            item.category = game.get('name')
        
        return item
    
    async def _extract_clip(self, clip_id: str) -> Optional[MediaItem]:
        """Extract a single clip."""
        operations = [
            {
                "operationName": "ClipMetadata",
                "variables": {"slug": clip_id},
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "6e465bb8446e2391644cf079851c0cb1b96928435a240f07ed4b240f0acc6f1b"
                    }
                }
            }
        ]
        
        data = await self._gql_request(operations)
        if not data or not data[0].get('data'):
            return None
        
        clip = data[0]['data'].get('clip')
        if not clip:
            return None
        
        item = MediaItem(
            title=clip.get('title', ''),
            url=f"https://clips.twitch.tv/{clip_id}",
            external_id=clip_id,
            platform=Platform.TWITCH,
            media_type=MediaType.CLIP,
            extractor=self.__class__.__name__,
        )
        
        # Duration
        if duration := clip.get('durationSeconds'):
            item.duration = int(duration)
        
        # Thumbnail
        item.thumbnail_url = clip.get('thumbnailURL')
        
        # Broadcaster (channel)
        if broadcaster := clip.get('broadcaster'):
            item.channel_name = broadcaster.get('displayName')
            item.channel_id = broadcaster.get('id')
            item.channel_url = f"https://twitch.tv/{broadcaster.get('login', '')}"
        
        # View count
        item.view_count = clip.get('viewCount')
        
        # Video URL
        if video_url := clip.get('videoQualities', [{}])[0].get('sourceURL'):
            item.stream_url = video_url
            item.streams.append(StreamInfo(
                url=video_url,
                quality=StreamQuality.UNKNOWN,
                protocol=StreamProtocol.PROGRESSIVE,
            ))
        
        return item
    
    async def _get_channel_vods(self, channel: str, limit: int = 20) -> List[MediaItem]:
        """Get VODs from a channel."""
        operations = [
            {
                "operationName": "FilterableVideoTower_Videos",
                "variables": {
                    "limit": min(limit, 30),
                    "channelOwnerLogin": channel,
                    "broadcastType": "ARCHIVE",
                    "videoSort": "TIME"
                },
                "extensions": {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "a937f1d22e269e39a03b509f65a7490f9fc247d7f83d6ac1421523e3b68c82e3"
                    }
                }
            }
        ]
        
        data = await self._gql_request(operations)
        if not data or not data[0].get('data'):
            return []
        
        user = data[0]['data'].get('user')
        if not user:
            return []
        
        videos = user.get('videos', {}).get('edges', [])
        items = []
        
        for edge in videos:
            node = edge.get('node', {})
            if not node:
                continue
            
            item = MediaItem(
                title=node.get('title', ''),
                url=f"https://twitch.tv/videos/{node.get('id')}",
                external_id=node.get('id'),
                platform=Platform.TWITCH,
                media_type=MediaType.VOD,
                extractor=self.__class__.__name__,
            )
            
            if length := node.get('lengthSeconds'):
                item.duration = int(length)
            
            if preview := node.get('previewThumbnailURL'):
                item.thumbnail_url = preview.replace('%{width}', '1280').replace('%{height}', '720')
            
            item.view_count = node.get('viewCount')
            item.channel_name = user.get('displayName')
            
            items.append(item)
        
        return items