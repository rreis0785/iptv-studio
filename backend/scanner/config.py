"""
Scanner configuration settings.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class NetworkConfig:
    """Network and HTTP settings."""
    
    timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Rate limiting
    requests_per_second: float = 2.0
    
    # User agent rotation
    user_agents: List[str] = field(default_factory=lambda: [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ])
    
    # Proxy settings
    proxies: List[str] = field(default_factory=lambda: [])
    proxy_file: Optional[str] = field(default_factory=lambda: os.getenv('PROXY_FILE'))
    
    def __post_init__(self):
        # Load proxies from env if not set
        if not self.proxies:
            # Try specific proxy env vars
            if p := os.getenv('HTTP_PROXY'):
                self.proxies.append(p)
            if p := os.getenv('HTTPS_PROXY'):
                if p not in self.proxies:
                    self.proxies.append(p)
            
            # Try comma-separated list
            if p_list := os.getenv('PROXY_LIST'):
                self.proxies.extend([p.strip() for p in p_list.split(',') if p.strip()])
                
            # Try loading from file
            if self.proxy_file and os.path.exists(self.proxy_file):
                try:
                    with open(self.proxy_file, 'r') as f:
                        file_proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                        self.proxies.extend(file_proxies)
                except Exception:
                    pass


@dataclass
class YouTubeConfig:
    """YouTube-specific settings."""
    
    # API key (optional, for higher rate limits)
    api_key: Optional[str] = field(default_factory=lambda: os.getenv('YOUTUBE_API_KEY'))
    
    # Extraction settings
    max_videos_per_channel: int = 50
    max_playlist_items: int = 100
    include_shorts: bool = False
    include_live_only: bool = False
    
    # Quality preferences
    preferred_quality: str = 'best'  # best, 1080p, 720p, 480p, worst
    prefer_hls: bool = True


@dataclass
class TwitchConfig:
    """Twitch-specific settings."""
    
    client_id: Optional[str] = field(default_factory=lambda: os.getenv('TWITCH_CLIENT_ID'))
    client_secret: Optional[str] = field(default_factory=lambda: os.getenv('TWITCH_CLIENT_SECRET'))
    
    include_vods: bool = True
    include_clips: bool = False
    max_vods: int = 20


@dataclass
class ScraperConfig:
    """Generic scraper settings."""
    
    # Content discovery
    follow_links: bool = True
    max_depth: int = 2
    max_pages: int = 10
    
    # Media detection
    detect_m3u8: bool = True
    detect_mp4: bool = True
    detect_embedded_players: bool = True
    detect_iframes: bool = True
    
    # Filtering
    min_duration: int = 0  # seconds, 0 = no minimum
    max_duration: int = 0  # seconds, 0 = no maximum
    
    # JavaScript rendering (requires playwright)
    use_browser: bool = False
    browser_timeout: int = 30000  # ms
    wait_for_network_idle: bool = True


@dataclass
class ScannerConfig:
    """Main scanner configuration."""
    
    network: NetworkConfig = field(default_factory=NetworkConfig)
    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    twitch: TwitchConfig = field(default_factory=TwitchConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    
    # Cache settings
    cache_enabled: bool = True
    cache_ttl: int = 3600  # seconds
    
    # Output
    auto_generate_thumbnails: bool = False
    extract_metadata: bool = True


# Global config instance
config = ScannerConfig()