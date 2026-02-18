"""
Utility functions for the transcoding server.

This module contains helper functions used across the application.
"""

import hashlib
import re
import secrets
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Protocols accepted as valid IPTV stream sources.
# Includes common IP-based streaming protocols beyond basic HTTP/RTMP.
# ---------------------------------------------------------------------------
_SUPPORTED_SCHEMES = frozenset((
    'http',
    'https',
    'rtmp',
    'rtmps',
    'rtsp',
    'rtsps',
    'udp',
    'rtp',
    'srt',
    'hls',   # some players pass hls:// explicitly
))


def generate_stream_id(url: str, prefix: str = "stream") -> str:
    """
    Generate a unique, collision-resistant stream ID from a URL.

    Uses a millisecond timestamp combined with a cryptographically random
    suffix so IDs remain unique even when the same URL is opened twice in
    rapid succession.

    Args:
        url: Source URL (used only for deterministic grouping if needed).
        prefix: ID prefix.

    Returns:
        Unique stream identifier, e.g. ``stream_1708123456789_3f9a1c2b``.
    """
    timestamp = int(time.time() * 1000)
    random_suffix = secrets.token_hex(4)   # 8 hex chars, cryptographically random
    return f"{prefix}_{timestamp}_{random_suffix}"


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a stream URL for use as an IPTV source.

    Accepted protocols: http, https, rtmp, rtmps, rtsp, rtsps,
    udp, rtp, srt, hls.

    Args:
        url: URL to validate.

    Returns:
        ``(True, None)`` when valid; ``(False, reason)`` otherwise.
    """
    if not url:
        return False, "URL is required"

    url = url.strip()

    try:
        parsed = urlparse(url)

        if not parsed.scheme:
            return False, "Invalid URL: missing scheme"

        if parsed.scheme not in _SUPPORTED_SCHEMES:
            supported = ', '.join(sorted(_SUPPORTED_SCHEMES))
            return False, f"Unsupported protocol '{parsed.scheme}'. Supported: {supported}"

        # udp/rtp/srt use host:port without a path; netloc may be empty when
        # urlparse sees e.g. "udp://@239.0.0.1:1234" — check host separately.
        host = parsed.hostname or parsed.netloc
        if not host:
            return False, "Invalid URL: missing host"

        return True, None

    except Exception as exc:
        return False, f"Invalid URL: {exc}"


def parse_duration(duration_str: str) -> Optional[float]:
    """
    Parse an FFmpeg duration string to seconds.

    Handles both decimal seconds (``"90.5"``) and the ``HH:MM:SS[.ms]``
    format produced by ffprobe (``"00:01:30.50"``).

    Args:
        duration_str: Duration string from ffprobe output.

    Returns:
        Duration in seconds, or ``None`` if parsing fails.
    """
    if not duration_str:
        return None

    stripped = duration_str.strip()

    # Fast path: plain float / integer string
    try:
        return float(stripped)
    except ValueError:
        pass

    # HH:MM:SS[.fractional] — anchored match to avoid partial hits
    match = re.fullmatch(r'(\d+):([0-5]\d):(\d{2}(?:\.\d+)?)', stripped)
    if match:
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    return None


def format_bytes(num_bytes: int) -> str:
    """
    Format a byte count to a human-readable string.

    Args:
        num_bytes: Number of bytes (may be negative).

    Returns:
        Formatted string, e.g. ``"1.5 GB"``.
    """
    value = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.

    Args:
        seconds: Duration in seconds (non-negative).

    Returns:
        Formatted string, e.g. ``"1h 30m 45s"``.
        Returns ``"0s"`` for zero or sub-second values.
    """
    if seconds < 0:
        seconds = 0.0

    if seconds < 60:
        return f"{seconds:.0f}s"

    total_seconds = int(seconds)
    mins, secs = divmod(total_seconds, 60)
    hours, mins = divmod(mins, 60)

    parts = []
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    if secs:
        parts.append(f"{secs}s")

    return " ".join(parts) or "0s"


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for safe use as a filename on Windows and POSIX.

    Args:
        name: Original name string.

    Returns:
        Sanitized filename, falling back to ``"unnamed"`` if the result
        would be empty.
    """
    # Strip characters that are illegal on Windows or meaningful on POSIX
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    # Collapse whitespace to underscores
    name = re.sub(r'\s+', '_', name)
    # Remove leading/trailing dots and underscores
    name = name.strip('._')
    # Enforce a safe maximum length (255 is the ext4/NTFS inode name limit)
    name = name[:255]

    return name or 'unnamed'