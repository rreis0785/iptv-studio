"""
Data models for the media scanner.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from uuid import uuid4


def generate_id() -> str:
    """Generate a unique identifier."""
    return uuid4().hex[:12]


def utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.utcnow()


# =============================================================================
# Enums
# =============================================================================

class MediaType(str, Enum):
    """Type of media content."""
    LIVE = "live"
    VOD = "vod"
    PLAYLIST = "playlist"
    CHANNEL = "channel"
    CLIP = "clip"
    SHORT = "short"
    UNKNOWN = "unknown"


class StreamQuality(str, Enum):
    """Stream quality levels."""
    QUALITY_4K = "4k"
    QUALITY_1440P = "1440p"
    QUALITY_1080P = "1080p"
    QUALITY_720P = "720p"
    QUALITY_480P = "480p"
    QUALITY_360P = "360p"
    QUALITY_240P = "240p"
    AUDIO_ONLY = "audio"
    UNKNOWN = "unknown"


class Platform(str, Enum):
    """Source platform."""
    YOUTUBE = "youtube"
    TWITCH = "twitch"
    VIMEO = "vimeo"
    DAILYMOTION = "dailymotion"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    RUMBLE = "rumble"
    KICK = "kick"
    DIRECT = "direct"
    WEBSITE = "website"
    RSS = "rss"
    UNKNOWN = "unknown"


class ScanStatus(str, Enum):
    """Scan operation status."""
    PENDING = "pending"
    SCANNING = "scanning"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StreamProtocol(str, Enum):
    """Stream protocol type."""
    HLS = "hls"
    DASH = "dash"
    RTMP = "rtmp"
    RTSP = "rtsp"
    HTTP = "http"
    PROGRESSIVE = "progressive"
    UNKNOWN = "unknown"


# =============================================================================
# Stream Info
# =============================================================================

@dataclass
class StreamInfo:
    """Information about a specific stream/quality variant."""
    
    url: str
    quality: StreamQuality = StreamQuality.UNKNOWN
    protocol: StreamProtocol = StreamProtocol.UNKNOWN
    
    # Technical details
    resolution: Optional[str] = None  # "1920x1080"
    width: Optional[int] = None
    height: Optional[int] = None
    bitrate: Optional[int] = None  # kbps
    fps: Optional[float] = None
    
    # Codecs
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    
    # HTTP options
    headers: Dict[str, str] = field(default_factory=dict)
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    
    # DRM
    is_drm_protected: bool = False
    drm_type: Optional[str] = None
    
    # Validity
    expires_at: Optional[datetime] = None
    is_temporary: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data['quality'] = self.quality.value
        data['protocol'] = self.protocol.value
        if self.expires_at:
            data['expires_at'] = self.expires_at.isoformat()
        return data


# =============================================================================
# Media Item
# =============================================================================

@dataclass
class MediaItem:
    """
    A discovered media item (video, stream, channel).
    
    This represents a single piece of media content that can be
    converted to an IPTV channel or VOD entry.
    """
    
    id: str = field(default_factory=generate_id)
    
    # Basic info
    title: str = ""
    description: Optional[str] = None
    url: str = ""  # Original URL
    
    # Type and source
    media_type: MediaType = MediaType.UNKNOWN
    platform: Platform = Platform.UNKNOWN
    
    # Stream URLs (may have multiple qualities)
    streams: List[StreamInfo] = field(default_factory=list)
    
    # Best/primary stream URL for direct use
    stream_url: Optional[str] = None
    
    # Display
    thumbnail_url: Optional[str] = None
    logo_url: Optional[str] = None
    
    # Channel/Author info
    channel_name: Optional[str] = None
    channel_id: Optional[str] = None
    channel_url: Optional[str] = None
    channel_logo: Optional[str] = None
    
    # Metadata
    duration: Optional[int] = None  # seconds
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    upload_date: Optional[datetime] = None
    
    # Categories
    category: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    # Live stream info
    is_live: bool = False
    is_upcoming: bool = False
    scheduled_start: Optional[datetime] = None
    viewer_count: Optional[int] = None
    
    # Language
    language: Optional[str] = None
    
    # External IDs
    external_id: Optional[str] = None  # Platform-specific ID
    
    # Age restriction
    is_age_restricted: bool = False
    
    # Extraction metadata
    extracted_at: datetime = field(default_factory=utcnow)
    extractor: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = field(default=None, repr=False)
    
    @property
    def best_stream(self) -> Optional[StreamInfo]:
        """Get the best quality stream."""
        if not self.streams:
            return None
        
        # Priority order for quality
        quality_order = [
            StreamQuality.QUALITY_4K,
            StreamQuality.QUALITY_1440P,
            StreamQuality.QUALITY_1080P,
            StreamQuality.QUALITY_720P,
            StreamQuality.QUALITY_480P,
            StreamQuality.QUALITY_360P,
            StreamQuality.QUALITY_240P,
        ]
        
        for quality in quality_order:
            for stream in self.streams:
                if stream.quality == quality:
                    return stream
        
        return self.streams[0] if self.streams else None
    
    @property
    def duration_formatted(self) -> Optional[str]:
        """Get formatted duration."""
        if not self.duration:
            return None
        hours, remainder = divmod(self.duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'url': self.url,
            'media_type': self.media_type.value,
            'platform': self.platform.value,
            'stream_url': self.stream_url or (self.best_stream.url if self.best_stream else None),
            'streams': [s.to_dict() for s in self.streams],
            'thumbnail_url': self.thumbnail_url,
            'logo_url': self.logo_url,
            'channel_name': self.channel_name,
            'channel_id': self.channel_id,
            'channel_url': self.channel_url,
            'duration': self.duration,
            'duration_formatted': self.duration_formatted,
            'view_count': self.view_count,
            'is_live': self.is_live,
            'is_upcoming': self.is_upcoming,
            'category': self.category,
            'tags': self.tags,
            'language': self.language,
            'external_id': self.external_id,
            'extracted_at': self.extracted_at.isoformat(),
        }
        
        if self.upload_date:
            data['upload_date'] = self.upload_date.isoformat()
        if self.scheduled_start:
            data['scheduled_start'] = self.scheduled_start.isoformat()
        
        return data
    
    def to_channel_dict(self, playlist_id: str, group_id: str = None) -> Dict[str, Any]:
        """Convert to IPTV channel creation format."""
        stream = self.best_stream
        
        return {
            'name': self.title,
            'url': stream.url if stream else self.stream_url or self.url,
            'playlist_id': playlist_id,
            'group_id': group_id,
            'logo_url': self.thumbnail_url or self.channel_logo,
            'tvg_name': self.title,
            'tvg_id': self.external_id,
            'stream_type': 'live' if self.is_live else 'vod',
            'user_agent': stream.user_agent if stream else None,
            'referrer': stream.referrer if stream else None,
            'http_headers': stream.headers if stream else {},
        }
    
    def to_vod_dict(self, playlist_id: str, group_id: str = None) -> Dict[str, Any]:
        """Convert to IPTV VOD creation format."""
        stream = self.best_stream
        
        return {
            'name': self.title,
            'url': stream.url if stream else self.stream_url or self.url,
            'playlist_id': playlist_id,
            'group_id': group_id,
            'content_type': 'video',
            'duration': self.duration,
            'poster_url': self.thumbnail_url,
            'plot': self.description,
            'genre': self.category,
            'user_agent': stream.user_agent if stream else None,
            'referrer': stream.referrer if stream else None,
        }


# =============================================================================
# Scan Result
# =============================================================================

@dataclass
class ScanResult:
    """
    Result of a media scan operation.
    
    Contains all discovered media items and metadata about the scan.
    """
    
    id: str = field(default_factory=generate_id)
    
    # Input
    url: str = ""
    platform: Platform = Platform.UNKNOWN
    
    # Status
    status: ScanStatus = ScanStatus.PENDING
    error_message: Optional[str] = None
    
    # Results
    items: List[MediaItem] = field(default_factory=list)
    
    # Pagination for large results
    total_count: int = 0
    has_more: bool = False
    next_page_token: Optional[str] = None
    
    # Source metadata
    source_title: Optional[str] = None
    source_description: Optional[str] = None
    source_thumbnail: Optional[str] = None
    source_channel: Optional[str] = None
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    
    # Statistics
    pages_scanned: int = 0
    requests_made: int = 0
    
    @property
    def item_count(self) -> int:
        """Number of items found."""
        return len(self.items)
    
    @property
    def live_count(self) -> int:
        """Number of live streams found."""
        return sum(1 for item in self.items if item.is_live)
    
    @property
    def vod_count(self) -> int:
        """Number of VOD items found."""
        return sum(1 for item in self.items if not item.is_live)
    
    @property
    def is_success(self) -> bool:
        """Check if scan was successful."""
        return self.status in (ScanStatus.COMPLETED, ScanStatus.PARTIAL)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            'id': self.id,
            'url': self.url,
            'platform': self.platform.value,
            'status': self.status.value,
            'error_message': self.error_message,
            'item_count': self.item_count,
            'live_count': self.live_count,
            'vod_count': self.vod_count,
            'total_count': self.total_count,
            'has_more': self.has_more,
            'source_title': self.source_title,
            'source_channel': self.source_channel,
            'pages_scanned': self.pages_scanned,
            'requests_made': self.requests_made,
            'items': [item.to_dict() for item in self.items],
        }
        
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        if self.duration_ms:
            data['duration_ms'] = self.duration_ms
        
        return data
    
    def to_channels(self, playlist_id: str, group_id: str = None) -> List[Dict[str, Any]]:
        """Convert all items to IPTV channel format."""
        return [
            item.to_channel_dict(playlist_id, group_id)
            for item in self.items
            if item.is_live
        ]
    
    def to_vod(self, playlist_id: str, group_id: str = None) -> List[Dict[str, Any]]:
        """Convert all items to IPTV VOD format."""
        return [
            item.to_vod_dict(playlist_id, group_id)
            for item in self.items
            if not item.is_live
        ]
    
    def filter_live(self) -> List[MediaItem]:
        """Get only live streams."""
        return [item for item in self.items if item.is_live]
    
    def filter_vod(self) -> List[MediaItem]:
        """Get only VOD content."""
        return [item for item in self.items if not item.is_live]
    
    def filter_by_platform(self, platform: Platform) -> List[MediaItem]:
        """Filter items by platform."""
        return [item for item in self.items if item.platform == platform]


# =============================================================================
# Scan Request
# =============================================================================

@dataclass
class ScanRequest:
    """Request parameters for a scan operation."""
    
    url: str
    
    # Options
    include_live: bool = True
    include_vod: bool = True
    max_items: int = 50
    
    # Quality filter
    min_quality: Optional[StreamQuality] = None
    
    # Platform hints
    force_platform: Optional[Platform] = None
    
    # Pagination
    page_token: Optional[str] = None
    
    # Depth for website scraping
    max_depth: int = 2
    follow_links: bool = True
    
    # Authentication (for some platforms)
    auth_token: Optional[str] = None
    cookies: Dict[str, str] = field(default_factory=dict)