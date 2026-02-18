"""
Main media scanner class.

Coordinates extractors to scan URLs and discover media content.
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Type

from scanner.config import config, ScannerConfig
from scanner.extractors import registry, BaseExtractor
from scanner.http_client import http_client
from scanner.models import (
    MediaItem,
    Platform,
    ScanRequest,
    ScanResult,
    ScanStatus,
)

logger = logging.getLogger(__name__)


class MediaScanner:
    """
    Main scanner class for discovering media content.
    
    Automatically selects the appropriate extractor based on URL
    and coordinates the extraction process.
    
    Example Usage:
        scanner = MediaScanner()
        
        # Scan a YouTube channel
        result = await scanner.scan("https://youtube.com/@channel")
        
        # Scan multiple URLs
        results = await scanner.scan_many([
            "https://youtube.com/watch?v=abc123",
            "https://twitch.tv/streamer",
            "https://example.com/live"
        ])
        
        # Convert results to IPTV format
        channels = result.to_channels(playlist_id="abc123")
    """
    
    def __init__(self, scanner_config: ScannerConfig = None):
        """
        Initialize the scanner.
        
        Args:
            scanner_config: Optional custom configuration
        """
        self.config = scanner_config or config
        self._registry = registry
    
    async def scan(
        self,
        url: str,
        include_live: bool = True,
        include_vod: bool = True,
        max_items: int = 50,
        max_depth: int = 2,
        follow_links: bool = True,
    ) -> ScanResult:
        """
        Scan a URL for media content.
        
        Args:
            url: URL to scan
            include_live: Include live streams
            include_vod: Include VOD content
            max_items: Maximum items to extract
            max_depth: Maximum depth for website crawling
            follow_links: Follow links on websites
            
        Returns:
            ScanResult with discovered media items
        """
        request = ScanRequest(
            url=url,
            include_live=include_live,
            include_vod=include_vod,
            max_items=max_items,
            max_depth=max_depth,
            follow_links=follow_links,
        )
        
        return await self._scan(request)
    
    async def _scan(self, request: ScanRequest) -> ScanResult:
        """Internal scan implementation."""
        logger.info(f"Scanning URL: {request.url}")
        
        # Get appropriate extractor
        extractor = self._get_extractor(request.url, request.force_platform)
        
        if not extractor:
            logger.warning(f"No extractor found for URL: {request.url}")
            return ScanResult(
                url=request.url,
                status=ScanStatus.FAILED,
                error_message="No suitable extractor found for this URL"
            )
        
        logger.debug(f"Using extractor: {extractor.__class__.__name__}")
        
        try:
            result = await extractor.extract(request)
            
            # Apply filters
            if not request.include_live:
                result.items = [i for i in result.items if not i.is_live]
            if not request.include_vod:
                result.items = [i for i in result.items if i.is_live]
            
            # Apply max items limit
            if len(result.items) > request.max_items:
                result.items = result.items[:request.max_items]
                result.has_more = True
            
            logger.info(
                f"Scan completed: {result.item_count} items found "
                f"({result.live_count} live, {result.vod_count} VOD)"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            return ScanResult(
                url=request.url,
                platform=extractor.PLATFORM,
                status=ScanStatus.FAILED,
                error_message=str(e)
            )
    
    async def scan_many(
        self,
        urls: List[str],
        **kwargs
    ) -> List[ScanResult]:
        """
        Scan multiple URLs concurrently.
        
        Args:
            urls: List of URLs to scan
            **kwargs: Arguments passed to scan()
            
        Returns:
            List of ScanResults in same order as input URLs
        """
        tasks = [self.scan(url, **kwargs) for url in urls]
        return await asyncio.gather(*tasks)
    
    def _get_extractor(
        self,
        url: str,
        force_platform: Platform = None
    ) -> Optional[BaseExtractor]:
        """Get the appropriate extractor for a URL."""
        if force_platform:
            # Find extractor for specified platform
            for extractor in self._registry.registered_extractors:
                if extractor.PLATFORM == force_platform:
                    return extractor()
        
        return self._registry.get_extractor(url)
    
    def detect_platform(self, url: str) -> Platform:
        """
        Detect the platform for a URL.
        
        Args:
            url: URL to analyze
            
        Returns:
            Detected Platform enum value
        """
        return self._registry.get_platform(url)
    
    def get_supported_platforms(self) -> List[Platform]:
        """Get list of supported platforms."""
        return [
            extractor.PLATFORM 
            for extractor in self._registry.registered_extractors
        ]
    
    async def probe_url(self, url: str) -> dict:
        """
        Probe a URL to get basic info without full extraction.
        
        Args:
            url: URL to probe
            
        Returns:
            Dictionary with URL info
        """
        platform = self.detect_platform(url)
        extractor = self._get_extractor(url)
        
        # Make a HEAD request to check accessibility
        response = await http_client.get(url)
        
        return {
            'url': url,
            'platform': platform.value,
            'extractor': extractor.__class__.__name__ if extractor else None,
            'accessible': response.success,
            'status_code': response.status_code,
            'content_type': response.headers.get('content-type', ''),
        }
    
    async def close(self) -> None:
        """Close the scanner and release resources."""
        await http_client.close()
    
    async def __aenter__(self) -> 'MediaScanner':
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Convenience function for quick scans
async def scan_url(url: str, **kwargs) -> ScanResult:
    """
    Convenience function to scan a single URL.
    
    Args:
        url: URL to scan
        **kwargs: Arguments passed to MediaScanner.scan()
        
    Returns:
        ScanResult with discovered media
        
    Example:
        result = await scan_url("https://youtube.com/@channel")
        for item in result.items:
            print(f"{item.title}: {item.stream_url}")
    """
    scanner = MediaScanner()
    try:
        return await scanner.scan(url, **kwargs)
    finally:
        await scanner.close()