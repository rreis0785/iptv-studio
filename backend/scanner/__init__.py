"""
Media Scanner Module
=====================
Scan websites and platforms for media content to add to IPTV playlists.

Supported Sources:
- YouTube (channels, playlists, videos)
- Twitch (channels, VODs)
- Vimeo (channels, videos)
- Dailymotion (channels, videos)
- Direct M3U8/MP4 links
- Generic website scraping for video content
- RSS/Atom feeds with media enclosures

Example Usage:
    from scanner import MediaScanner
    
    scanner = MediaScanner()
    
    # Scan a YouTube channel
    results = await scanner.scan("https://youtube.com/@channel")
    
    # Scan a website for streams
    results = await scanner.scan("https://example.com/live")
    
    # Convert to IPTV channels
    channels = results.to_channels(playlist_id="abc123")
"""

from scanner.scanner import MediaScanner
from scanner.models import (
    ScanResult,
    MediaItem,
    MediaType,
    StreamQuality,
    ScanStatus,
)
from scanner.extractors import (
    BaseExtractor,
    YouTubeExtractor,
    TwitchExtractor,
    VimeoExtractor,
    GenericExtractor,
)

__version__ = '1.0.0'
__all__ = [
    'MediaScanner',
    'ScanResult',
    'MediaItem',
    'MediaType',
    'StreamQuality',
    'ScanStatus',
    'BaseExtractor',
    'YouTubeExtractor',
    'TwitchExtractor',
    'VimeoExtractor',
    'GenericExtractor',
]