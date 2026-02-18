"""
Media extractors package.

Contains platform-specific extractors for discovering media content.
"""

from scanner.extractors.base import (
    BaseExtractor,
    ExtractorRegistry,
    registry,
    register_extractor,
)
from scanner.extractors.youtube import YouTubeExtractor
from scanner.extractors.twitch import TwitchExtractor
from scanner.extractors.vimeo import VimeoExtractor
from scanner.extractors.generic import GenericExtractor
from scanner.extractors.playlist import PlaylistExtractor

__all__ = [
    'BaseExtractor',
    'ExtractorRegistry',
    'registry',
    'register_extractor',
    'YouTubeExtractor',
    'TwitchExtractor',
    'VimeoExtractor',
    'VimeoExtractor',
    'GenericExtractor',
    'PlaylistExtractor',
]