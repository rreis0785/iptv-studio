"""
IPTV Transcoding Backend Server
================================
Real-time video transcoding using FFmpeg for browser compatibility.

This package provides a Flask-based server that receives IPTV stream URLs
and transcodes them on-the-fly to browser-compatible formats (H.264 + AAC).

Key Features:
- Smart transcoding (copy H.264 video, transcode audio only)
- Multiple concurrent streams with thread-safe management
- Automatic cleanup of idle/dead processes
- Health monitoring and stream statistics
- RESTful API endpoints

Example Usage::

    from transcoder import create_app

    app = create_app()
    app.run(host='0.0.0.0', port=5000)
"""

from importlib.metadata import PackageNotFoundError, version

from transcoder.app import create_app
from transcoder.config import Config
from transcoder.manager import StreamManager
from transcoder.models import StreamInfo, StreamStatus
from transcoder.transcoder import StreamTranscoder

try:
    __version__: str = version("transcoder")
except PackageNotFoundError:
    # Package is not installed (running from source tree)
    __version__ = "2.0.0"

__all__ = [
    "__version__",
    "create_app",
    "Config",
    "StreamStatus",
    "StreamInfo",
    "StreamTranscoder",
    "StreamManager",
]