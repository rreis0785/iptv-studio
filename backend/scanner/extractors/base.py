"""
Base extractor and extractor registry.

Extractors are responsible for fetching and parsing media content
from specific platforms or website types.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Pattern, Type
from urllib.parse import urlparse

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

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """
    Abstract base class for media extractors.
    
    Each extractor handles a specific platform or type of content.
    Subclasses must implement:
    - PLATFORM: The platform this extractor handles
    - URL_PATTERNS: Regex patterns to match URLs
    - extract(): The main extraction method
    """
    
    PLATFORM: Platform = Platform.UNKNOWN
    URL_PATTERNS: List[Pattern] = []
    
    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @classmethod
    def can_handle(cls, url: str) -> bool:
        """Check if this extractor can handle the given URL."""
        for pattern in cls.URL_PATTERNS:
            if pattern.search(url):
                return True
        return False
    
    @classmethod
    def match_url(cls, url: str) -> Optional[re.Match]:
        """Get the first matching pattern match object."""
        for pattern in cls.URL_PATTERNS:
            if match := pattern.search(url):
                return match
        return None
    
    @abstractmethod
    async def extract(self, request: ScanRequest) -> ScanResult:
        """
        Extract media items from the URL.
        
        Args:
            request: Scan request with URL and options
            
        Returns:
            ScanResult with discovered media items
        """
        pass
    
    async def extract_stream_url(self, item: MediaItem) -> Optional[str]:
        """
        Extract the actual stream URL for a media item.
        
        Some platforms require additional requests to get the stream URL.
        Override this method for platforms that need it.
        """
        return item.stream_url
    
    def _create_result(self, request: ScanRequest) -> ScanResult:
        """Create a new ScanResult for this extraction."""
        return ScanResult(
            url=request.url,
            platform=self.PLATFORM,
            status=ScanStatus.SCANNING,
        )
    
    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse duration string to seconds."""
        if not duration_str:
            return None
        
        # Try ISO 8601 duration (PT1H2M3S)
        iso_match = re.match(
            r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?',
            duration_str
        )
        if iso_match:
            hours = int(iso_match.group(1) or 0)
            minutes = int(iso_match.group(2) or 0)
            seconds = int(iso_match.group(3) or 0)
            return hours * 3600 + minutes * 60 + seconds
        
        # Try HH:MM:SS or MM:SS
        time_match = re.match(r'(?:(\d+):)?(\d+):(\d+)', duration_str)
        if time_match:
            hours = int(time_match.group(1) or 0)
            minutes = int(time_match.group(2))
            seconds = int(time_match.group(3))
            return hours * 3600 + minutes * 60 + seconds
        
        # Try plain seconds
        try:
            return int(float(duration_str))
        except ValueError:
            return None
    
    def _detect_quality(self, height: int = None, label: str = None) -> StreamQuality:
        """Detect stream quality from height or label."""
        if height:
            if height >= 2160:
                return StreamQuality.QUALITY_4K
            elif height >= 1440:
                return StreamQuality.QUALITY_1440P
            elif height >= 1080:
                return StreamQuality.QUALITY_1080P
            elif height >= 720:
                return StreamQuality.QUALITY_720P
            elif height >= 480:
                return StreamQuality.QUALITY_480P
            elif height >= 360:
                return StreamQuality.QUALITY_360P
            else:
                return StreamQuality.QUALITY_240P
        
        if label:
            label_lower = label.lower()
            if '4k' in label_lower or '2160' in label_lower:
                return StreamQuality.QUALITY_4K
            elif '1440' in label_lower:
                return StreamQuality.QUALITY_1440P
            elif '1080' in label_lower:
                return StreamQuality.QUALITY_1080P
            elif '720' in label_lower:
                return StreamQuality.QUALITY_720P
            elif '480' in label_lower:
                return StreamQuality.QUALITY_480P
            elif '360' in label_lower:
                return StreamQuality.QUALITY_360P
            elif '240' in label_lower:
                return StreamQuality.QUALITY_240P
            elif 'audio' in label_lower:
                return StreamQuality.AUDIO_ONLY
        
        return StreamQuality.UNKNOWN
    
    def _detect_protocol(self, url: str) -> StreamProtocol:
        """Detect stream protocol from URL."""
        url_lower = url.lower()
        
        if '.m3u8' in url_lower or 'hls' in url_lower:
            return StreamProtocol.HLS
        elif '.mpd' in url_lower or 'dash' in url_lower:
            return StreamProtocol.DASH
        elif url_lower.startswith('rtmp://'):
            return StreamProtocol.RTMP
        elif url_lower.startswith('rtsp://'):
            return StreamProtocol.RTSP
        elif any(ext in url_lower for ext in ['.mp4', '.mkv', '.webm', '.avi']):
            return StreamProtocol.PROGRESSIVE
        elif url_lower.startswith(('http://', 'https://')):
            return StreamProtocol.HTTP
        
        return StreamProtocol.UNKNOWN


class ExtractorRegistry:
    """
    Registry of available extractors.
    
    Automatically selects the appropriate extractor for a given URL.
    """
    
    def __init__(self):
        self._extractors: List[Type[BaseExtractor]] = []
        self._instances: Dict[Type[BaseExtractor], BaseExtractor] = {}
    
    def register(self, extractor_class: Type[BaseExtractor]) -> None:
        """Register an extractor class."""
        if extractor_class not in self._extractors:
            self._extractors.append(extractor_class)
            logger.debug(f"Registered extractor: {extractor_class.__name__}")
    
    def get_extractor(self, url: str) -> Optional[BaseExtractor]:
        """Get an extractor instance that can handle the URL."""
        for extractor_class in self._extractors:
            if extractor_class.can_handle(url):
                # Return cached instance
                if extractor_class not in self._instances:
                    self._instances[extractor_class] = extractor_class()
                return self._instances[extractor_class]
        return None
    
    def get_platform(self, url: str) -> Platform:
        """Detect the platform for a URL."""
        extractor = self.get_extractor(url)
        if extractor:
            return extractor.PLATFORM
        return Platform.UNKNOWN
    
    @property
    def registered_extractors(self) -> List[Type[BaseExtractor]]:
        """Get list of registered extractor classes."""
        return self._extractors.copy()


# Global registry
registry = ExtractorRegistry()


def register_extractor(cls: Type[BaseExtractor]) -> Type[BaseExtractor]:
    """Decorator to register an extractor class."""
    registry.register(cls)
    return cls