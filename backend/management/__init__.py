"""
IPTV Playlist Management Backend
=================================
CRUD operations for IPTV playlists, channels, EPG, and VOD content.

This package provides a RESTful API for managing:
- Playlists (M3U/M3U8 collections)
- Live Stream Channels
- Video on Demand (VOD) content
- EPG/TVG (Electronic Program Guide) data
- Channel Groups/Categories
- Stream Sources

Example Usage:
    from management import create_app
    
    app = create_app()
    app.run(host='0.0.0.0', port=5000)
"""

from management.app import create_app
from management.config import Config

__version__ = '1.0.0'
__all__ = [
    'create_app',
    'Config',
]