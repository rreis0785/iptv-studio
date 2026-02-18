"""
Configuration settings for the IPTV backend.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class ServerConfig:
    """Flask server configuration."""
    
    host: str = field(default_factory=lambda: os.getenv('HOST', '0.0.0.0'))
    port: int = field(default_factory=lambda: int(os.getenv('PORT', '5000')))
    debug: bool = field(default_factory=lambda: os.getenv('DEBUG', '').lower() == 'true')
    
    # CORS settings
    cors_origins: str = '*'
    cors_methods: List[str] = field(default_factory=lambda: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
    cors_headers: List[str] = field(default_factory=lambda: ['Content-Type', 'Authorization'])


@dataclass
class StorageConfig:
    """Storage configuration."""
    
    # Backend type: 'memory' or 'json'
    backend: str = field(default_factory=lambda: os.getenv('STORAGE_BACKEND', 'json'))
    
    # Directory for JSON file storage
    data_dir: str = field(default_factory=lambda: os.getenv('DATA_DIR', './data'))
    
    # Auto-save on every write operation
    auto_save: bool = True
    
    # Future database settings
    db_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', ''))
    

@dataclass 
class PlaylistConfig:
    """Playlist-related configuration."""
    
    # Default values for new channels
    default_tvg_shift: int = 0
    default_catchup_days: int = 7
    
    # Validation limits
    max_channels_per_playlist: int = 10000
    max_groups_per_playlist: int = 500
    max_epg_programs_per_channel: int = 1000
    
    # Supported stream protocols
    supported_protocols: tuple = ('http', 'https', 'rtmp', 'rtsp', 'udp', 'rtp')


@dataclass
class AuthConfig:
    """API authentication configuration."""
    
    api_key: str = field(default_factory=lambda: os.getenv('API_KEY', ''))
    enabled: bool = field(default_factory=lambda: bool(os.getenv('API_KEY', '')))


@dataclass
class LogConfig:
    """Logging configuration."""
    
    level: int = field(default_factory=lambda: getattr(
        logging, 
        os.getenv('LOG_LEVEL', 'INFO').upper(), 
        logging.INFO
    ))
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


@dataclass
class Config:
    """Main configuration container."""
    
    server: ServerConfig = field(default_factory=ServerConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    playlist: PlaylistConfig = field(default_factory=PlaylistConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    log: LogConfig = field(default_factory=LogConfig)


# Global config instance
config = Config()