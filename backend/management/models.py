"""
Data models for IPTV playlist management.

This module defines all entity models used in the IPTV system:
- Playlist: Container for channels and VOD content
- Channel: Live stream channel with EPG support
- VOD: Video on Demand content
- EPGProgram: TV program schedule entry
- Group: Channel/VOD categorization
- StreamSource: Alternative stream sources
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from uuid import uuid4


def generate_id() -> str:
    """Generate a unique identifier."""
    return uuid4().hex[:12]


def utcnow() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# Enums
# =============================================================================

class StreamType(str, Enum):
    """Type of stream content."""
    LIVE = "live"
    VOD = "vod"
    SERIES = "series"
    

class StreamStatus(str, Enum):
    """Status of a stream."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    UNKNOWN = "unknown"


class ContentRating(str, Enum):
    """Content rating categories."""
    TV_Y = "TV-Y"
    TV_Y7 = "TV-Y7"
    TV_G = "TV-G"
    TV_PG = "TV-PG"
    TV_14 = "TV-14"
    TV_MA = "TV-MA"
    UNRATED = "unrated"


class CatchupType(str, Enum):
    """Catchup/Timeshift type."""
    NONE = "none"
    DEFAULT = "default"
    APPEND = "append"
    SHIFT = "shift"
    FLUSSONIC = "flussonic"
    XSTREAM = "xstream"


# =============================================================================
# Base Model
# =============================================================================

@dataclass
class BaseModel:
    """Base class for all models with common fields."""
    
    id: str = field(default_factory=generate_id)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    
    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {}
        for key, value in asdict(self).items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, Enum):
                data[key] = value.value
            elif isinstance(value, list):
                data[key] = [
                    item.to_dict() if hasattr(item, 'to_dict') else item
                    for item in value
                ]
            else:
                data[key] = value
        return data
    
    def update(self, **kwargs) -> None:
        """Update fields from keyword arguments."""
        for key, value in kwargs.items():
            if hasattr(self, key) and key not in ('id', 'created_at'):
                setattr(self, key, value)
        self.touch()


# =============================================================================
# Group Model
# =============================================================================

@dataclass
class Group(BaseModel):
    """
    Channel/VOD group (category).
    
    Groups organize channels and VOD content into categories
    like "Sports", "News", "Movies", etc.
    
    Attributes:
        name: Group display name
        slug: URL-friendly identifier
        playlist_id: Parent playlist ID
        order: Sort order within playlist
        logo_url: Group logo/icon URL
        parent_id: Parent group ID for nested groups
        is_hidden: Hide group from display
    """
    
    name: str = ""
    slug: str = ""
    playlist_id: str = ""
    order: int = 0
    logo_url: Optional[str] = None
    parent_id: Optional[str] = None
    is_hidden: bool = False
    
    # Metadata
    channel_count: int = 0
    vod_count: int = 0
    
    def __post_init__(self):
        if not self.slug and self.name:
            self.slug = self.name.lower().replace(' ', '-')


# =============================================================================
# EPG Program Model
# =============================================================================

@dataclass
class EPGProgram(BaseModel):
    """
    EPG (Electronic Program Guide) program entry.
    
    Represents a single TV program in the schedule.
    
    Attributes:
        channel_id: Associated channel ID
        title: Program title
        start_time: Program start time
        end_time: Program end time
        description: Program description
        category: Program category/genre
        episode_info: Episode details (season, episode, etc.)
        rating: Content rating
        poster_url: Program poster/thumbnail
        is_new: Flag for new episodes
        is_live: Flag for live programs
    """
    
    channel_id: str = ""
    title: str = ""
    start_time: datetime = field(default_factory=utcnow)
    end_time: datetime = field(default_factory=utcnow)
    
    # Details
    description: Optional[str] = None
    category: Optional[str] = None
    sub_title: Optional[str] = None
    
    # Episode info
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_title: Optional[str] = None
    
    # Media
    poster_url: Optional[str] = None
    icon_url: Optional[str] = None
    
    # Flags
    rating: ContentRating = ContentRating.UNRATED
    is_new: bool = False
    is_live: bool = False
    is_premiere: bool = False
    is_finale: bool = False
    
    # Credits
    directors: List[str] = field(default_factory=list)
    actors: List[str] = field(default_factory=list)
    writers: List[str] = field(default_factory=list)
    
    @property
    def duration_minutes(self) -> int:
        """Get program duration in minutes."""
        if self.end_time and self.start_time:
            return int((self.end_time - self.start_time).total_seconds() / 60)
        return 0
    
    @property
    def is_current(self) -> bool:
        """Check if program is currently airing."""
        now = utcnow()
        return self.start_time <= now <= self.end_time
    
    @property
    def episode_string(self) -> Optional[str]:
        """Get formatted episode string (e.g., 'S01E05')."""
        if self.season and self.episode:
            return f"S{self.season:02d}E{self.episode:02d}"
        elif self.episode:
            return f"E{self.episode:02d}"
        return None


# =============================================================================
# Stream Source Model
# =============================================================================

@dataclass
class StreamSource(BaseModel):
    """
    Alternative stream source/mirror.
    
    Channels and VOD can have multiple sources for redundancy.
    
    Attributes:
        channel_id: Associated channel/VOD ID
        url: Stream URL
        priority: Source priority (lower = higher priority)
        is_primary: Is this the primary source
        quality: Stream quality label
        user_agent: Custom user agent
        referrer: Custom referrer header
    """
    
    channel_id: str = ""
    url: str = ""
    priority: int = 0
    is_primary: bool = False
    
    # Quality info
    quality: Optional[str] = None  # "HD", "SD", "4K", etc.
    resolution: Optional[str] = None  # "1920x1080"
    bitrate: Optional[int] = None  # kbps
    
    # HTTP headers
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    http_headers: Dict[str, str] = field(default_factory=dict)
    
    # Status
    status: StreamStatus = StreamStatus.UNKNOWN
    last_checked: Optional[datetime] = None
    error_message: Optional[str] = None


# =============================================================================
# Channel Model (Live Streams)
# =============================================================================

@dataclass
class Channel(BaseModel):
    """
    Live stream channel.
    
    Represents a single IPTV channel with full M3U attributes support.
    
    M3U Attributes Mapping:
        tvg-id -> tvg_id
        tvg-name -> tvg_name  
        tvg-logo -> logo_url
        tvg-chno -> channel_number
        tvg-shift -> tvg_shift
        group-title -> group_id (resolved)
        catchup -> catchup_type
        catchup-source -> catchup_source
        catchup-days -> catchup_days
    
    Attributes:
        name: Channel display name
        url: Primary stream URL
        playlist_id: Parent playlist ID
        group_id: Channel group/category ID
        
        # TVG/EPG
        tvg_id: EPG channel identifier
        tvg_name: EPG channel name
        tvg_shift: EPG time shift in hours
        
        # Display
        logo_url: Channel logo URL
        channel_number: Logical channel number
        
        # Catchup/Timeshift
        catchup_type: Type of catchup support
        catchup_source: Catchup URL template
        catchup_days: Days of catchup available
        
        # Metadata
        language: Channel language code
        country: Channel country code
        is_favorite: User favorite flag
        is_hidden: Hide from display
        is_locked: Parental lock
    """
    
    # Basic info
    name: str = ""
    url: str = ""
    playlist_id: str = ""
    group_id: Optional[str] = None
    
    # TVG/EPG attributes
    tvg_id: Optional[str] = None
    tvg_name: Optional[str] = None
    tvg_shift: int = 0
    
    # Display
    logo_url: Optional[str] = None
    channel_number: Optional[int] = None
    order: int = 0
    
    # Catchup/Timeshift
    catchup_type: CatchupType = CatchupType.NONE
    catchup_source: Optional[str] = None
    catchup_days: int = 0
    
    # Stream info
    stream_type: StreamType = StreamType.LIVE
    status: StreamStatus = StreamStatus.UNKNOWN
    
    # HTTP options
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    http_headers: Dict[str, str] = field(default_factory=dict)
    
    # Metadata
    language: Optional[str] = None
    country: Optional[str] = None
    rating: ContentRating = ContentRating.UNRATED
    
    # Flags
    is_favorite: bool = False
    is_hidden: bool = False
    is_locked: bool = False
    is_adult: bool = False
    
    # Related data (not stored, populated on read)
    group: Optional[Group] = field(default=None, repr=False)
    sources: List[StreamSource] = field(default_factory=list)
    current_program: Optional[EPGProgram] = field(default=None, repr=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None relationships."""
        data = super().to_dict()
        # Remove unpopulated relationships
        if data.get('group') is None:
            del data['group']
        if data.get('current_program') is None:
            del data['current_program']
        if not data.get('sources'):
            del data['sources']
        return data
    
    def to_m3u_extinf(self) -> str:
        """Generate M3U EXTINF line for this channel."""
        attrs = []
        
        if self.tvg_id:
            attrs.append(f'tvg-id="{self.tvg_id}"')
        if self.tvg_name:
            attrs.append(f'tvg-name="{self.tvg_name}"')
        if self.logo_url:
            attrs.append(f'tvg-logo="{self.logo_url}"')
        if self.channel_number:
            attrs.append(f'tvg-chno="{self.channel_number}"')
        if self.tvg_shift:
            attrs.append(f'tvg-shift="{self.tvg_shift}"')
        if self.group_id:
            attrs.append(f'group-title="{self.group_id}"')
        if self.catchup_type != CatchupType.NONE:
            attrs.append(f'catchup="{self.catchup_type.value}"')
            if self.catchup_source:
                attrs.append(f'catchup-source="{self.catchup_source}"')
            if self.catchup_days:
                attrs.append(f'catchup-days="{self.catchup_days}"')
        
        attr_str = ' '.join(attrs)
        return f'#EXTINF:-1 {attr_str},{self.name}'


# =============================================================================
# VOD Model (Video on Demand)
# =============================================================================

@dataclass
class VOD(BaseModel):
    """
    Video on Demand content.
    
    Represents movies, series episodes, or other on-demand content.
    
    Attributes:
        name: Content title
        url: Stream URL
        playlist_id: Parent playlist ID
        group_id: Category/group ID
        
        # Media info
        duration: Duration in seconds
        year: Release year
        genre: Content genre
        director: Director name
        cast: Cast list
        
        # Series info
        series_id: Parent series ID (for episodes)
        season: Season number
        episode: Episode number
        
        # Display
        poster_url: Poster/cover image
        backdrop_url: Background image
        trailer_url: Trailer URL
        
        # Metadata
        plot: Plot description
        rating: Content rating
        imdb_id: IMDB identifier
        tmdb_id: TMDB identifier
    """
    
    # Basic info
    name: str = ""
    url: str = ""
    playlist_id: str = ""
    group_id: Optional[str] = None
    
    # Type
    stream_type: StreamType = StreamType.VOD
    content_type: str = "movie"  # movie, episode, documentary, etc.
    
    # Media info
    duration: Optional[int] = None  # seconds
    year: Optional[int] = None
    genre: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    
    # Credits
    director: Optional[str] = None
    cast: List[str] = field(default_factory=list)
    writers: List[str] = field(default_factory=list)
    studio: Optional[str] = None
    
    # Series info
    series_id: Optional[str] = None
    series_name: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_title: Optional[str] = None
    
    # Display
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    trailer_url: Optional[str] = None
    
    # Metadata
    plot: Optional[str] = None
    tagline: Optional[str] = None
    rating: ContentRating = ContentRating.UNRATED
    user_rating: Optional[float] = None  # 0-10
    votes: Optional[int] = None
    
    # External IDs
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    
    # Stream info
    status: StreamStatus = StreamStatus.UNKNOWN
    quality: Optional[str] = None
    resolution: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    container: Optional[str] = None
    
    # HTTP options
    user_agent: Optional[str] = None
    referrer: Optional[str] = None
    http_headers: Dict[str, str] = field(default_factory=dict)
    
    # Language
    language: Optional[str] = None
    subtitles: List[str] = field(default_factory=list)
    audio_tracks: List[str] = field(default_factory=list)
    
    # Flags
    is_favorite: bool = False
    is_watched: bool = False
    is_hidden: bool = False
    is_locked: bool = False
    is_adult: bool = False
    
    # Watch progress
    watch_position: int = 0  # seconds
    watch_completed: bool = False
    last_watched: Optional[datetime] = None
    
    # Related data
    group: Optional[Group] = field(default=None, repr=False)
    sources: List[StreamSource] = field(default_factory=list)
    
    @property
    def duration_formatted(self) -> Optional[str]:
        """Get formatted duration (e.g., '2h 15m')."""
        if not self.duration:
            return None
        hours, remainder = divmod(self.duration, 3600)
        minutes = remainder // 60
        if hours:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
    
    @property
    def episode_string(self) -> Optional[str]:
        """Get formatted episode string (e.g., 'S01E05')."""
        if self.season and self.episode:
            return f"S{self.season:02d}E{self.episode:02d}"
        elif self.episode:
            return f"E{self.episode:02d}"
        return None
    
    @property
    def watch_progress_percent(self) -> float:
        """Get watch progress as percentage."""
        if self.duration and self.watch_position:
            return min(100.0, (self.watch_position / self.duration) * 100)
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None relationships."""
        data = super().to_dict()
        if data.get('group') is None:
            del data['group']
        if not data.get('sources'):
            del data['sources']
        # Add computed fields
        data['duration_formatted'] = self.duration_formatted
        data['episode_string'] = self.episode_string
        data['watch_progress_percent'] = self.watch_progress_percent
        return data


# =============================================================================
# Series Model
# =============================================================================

@dataclass
class Series(BaseModel):
    """
    TV Series container for VOD episodes.
    
    Attributes:
        name: Series title
        playlist_id: Parent playlist ID
        group_id: Category/group ID
        year: Release year
        seasons: Number of seasons
        episodes: Total episode count
    """
    
    name: str = ""
    playlist_id: str = ""
    group_id: Optional[str] = None
    
    # Info
    year: Optional[int] = None
    end_year: Optional[int] = None
    seasons_count: int = 0
    episodes_count: int = 0
    
    # Display
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None
    
    # Metadata
    plot: Optional[str] = None
    genre: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    rating: ContentRating = ContentRating.UNRATED
    user_rating: Optional[float] = None
    
    # External IDs
    imdb_id: Optional[str] = None
    tmdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    
    # Status
    status: str = "unknown"  # running, ended, canceled
    
    # Related episodes (populated on read)
    episodes: List[VOD] = field(default_factory=list, repr=False)


# =============================================================================
# Playlist Model
# =============================================================================

@dataclass
class Playlist(BaseModel):
    """
    IPTV Playlist container.
    
    A playlist is a collection of channels, VOD content, and groups.
    Corresponds to an M3U/M3U8 file.
    
    Attributes:
        name: Playlist display name
        description: Playlist description
        url: Source M3U URL (if imported)
        
        # EPG
        epg_url: EPG/XMLTV URL
        epg_shift: Global EPG time shift
        
        # Stats
        channel_count: Number of live channels
        vod_count: Number of VOD items
        group_count: Number of groups
        
        # Sync
        auto_sync: Enable auto-sync from URL
        sync_interval: Sync interval in hours
        last_synced: Last sync timestamp
    """
    
    name: str = ""
    description: Optional[str] = None
    
    # Source
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    
    # EPG settings
    epg_url: Optional[str] = None
    epg_shift: int = 0
    
    # M3U metadata
    x_tvg_url: Optional[str] = None
    url_tvg: Optional[str] = None
    
    # Counts (computed)
    channel_count: int = 0
    vod_count: int = 0
    series_count: int = 0
    group_count: int = 0
    
    # Sync settings
    auto_sync: bool = False
    sync_interval: int = 24  # hours
    last_synced: Optional[datetime] = None
    sync_error: Optional[str] = None
    
    # Flags
    is_active: bool = True
    is_default: bool = False
    
    # Related data (populated on read)
    groups: List[Group] = field(default_factory=list, repr=False)
    
    @property
    def total_items(self) -> int:
        """Get total number of items (channels + VOD)."""
        return self.channel_count + self.vod_count
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = super().to_dict()
        data['total_items'] = self.total_items
        if not data.get('groups'):
            del data['groups']
        return data
    
    def to_m3u_header(self) -> str:
        """Generate M3U header for this playlist."""
        header = '#EXTM3U'
        
        if self.x_tvg_url:
            header += f' x-tvg-url="{self.x_tvg_url}"'
        elif self.epg_url:
            header += f' x-tvg-url="{self.epg_url}"'
        
        if self.url_tvg:
            header += f' url-tvg="{self.url_tvg}"'
        
        return header