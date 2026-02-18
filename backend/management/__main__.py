#!/usr/bin/env python3
"""
IPTV Playlist Management Backend - Entry Point

Usage:
    python -m management
    python run.py
    
Environment Variables:
    HOST - Server host (default: 0.0.0.0)
    PORT - Server port (default: 5000)
    DEBUG - Enable debug mode (default: false)
    LOG_LEVEL - Logging level (default: INFO)
    API_KEY - API key for authentication (optional)
    DATA_DIR - Directory for JSON data persistence (default: ./data)
"""

from management.app import create_app
from management.config import config


def print_banner():
    """Print startup banner."""
    print("=" * 70)
    print("📺 IPTV PLAYLIST MANAGEMENT BACKEND")
    print("=" * 70)
    print()


def print_config():
    """Print current configuration."""
    print("⚙️  Configuration:")
    print(f"  Host:          {config.server.host}")
    print(f"  Port:          {config.server.port}")
    print(f"  Debug:         {config.server.debug}")
    print(f"  Storage:       {config.storage.backend}")
    print(f"  Auth:          {'enabled' if config.auth.enabled else 'disabled'}")
    print()


def print_endpoints():
    """Print available API endpoints."""
    base = f"http://{config.server.host}:{config.server.port}"
    
    print("📡 API Endpoints:")
    print()
    print("  Health & Stats:")
    print(f"    GET  {base}/api/health")
    print(f"    GET  {base}/api/stats")
    print()
    print("  Playlists:")
    print(f"    GET    {base}/api/playlists")
    print(f"    POST   {base}/api/playlists")
    print(f"    GET    {base}/api/playlists/<id>")
    print(f"    PUT    {base}/api/playlists/<id>")
    print(f"    DELETE {base}/api/playlists/<id>")
    print(f"    GET    {base}/api/playlists/<id>/export")
    print()
    print("  Channels (Live Streams):")
    print(f"    GET    {base}/api/channels")
    print(f"    POST   {base}/api/channels")
    print(f"    POST   {base}/api/channels/bulk          (bulk create)")
    print(f"    POST   {base}/api/channels/bulk-update    (bulk update)")
    print(f"    POST   {base}/api/channels/bulk-delete    (bulk delete)")
    print(f"    GET    {base}/api/channels/<id>")
    print(f"    PUT    {base}/api/channels/<id>")
    print(f"    DELETE {base}/api/channels/<id>")
    print(f"    GET    {base}/api/channels/search?q=<query>")
    print(f"    GET    {base}/api/channels/favorites")
    print()
    print("  VOD (Video on Demand):")
    print(f"    GET    {base}/api/vod")
    print(f"    POST   {base}/api/vod")
    print(f"    POST   {base}/api/vod/bulk                (bulk create)")
    print(f"    POST   {base}/api/vod/bulk-update          (bulk update)")
    print(f"    POST   {base}/api/vod/bulk-delete           (bulk delete)")
    print(f"    GET    {base}/api/vod/<id>")
    print(f"    PUT    {base}/api/vod/<id>")
    print(f"    DELETE {base}/api/vod/<id>")
    print(f"    GET    {base}/api/vod/search?q=<query>")
    print(f"    GET    {base}/api/vod/continue-watching")
    print(f"    POST   {base}/api/vod/<id>/progress")
    print()
    print("  Groups (Categories):")
    print(f"    GET    {base}/api/groups")
    print(f"    POST   {base}/api/groups")
    print(f"    POST   {base}/api/groups/bulk              (bulk create)")
    print(f"    GET    {base}/api/groups/<id>")
    print(f"    PUT    {base}/api/groups/<id>")
    print(f"    DELETE {base}/api/groups/<id>")
    print()
    print("  EPG (Program Guide):")
    print(f"    GET    {base}/api/epg?channel_id=<id>")
    print(f"    POST   {base}/api/epg")
    print(f"    POST   {base}/api/epg/bulk")
    print(f"    GET    {base}/api/epg/schedule/<channel_id>")
    print(f"    GET    {base}/api/epg/current?channel_id=<id>")
    print()
    print("  Series:")
    print(f"    GET    {base}/api/series")
    print(f"    POST   {base}/api/series")
    print(f"    GET    {base}/api/series/<id>")
    print(f"    GET    {base}/api/series/<id>/episodes")
    print()
    print("  Stream Sources:")
    print(f"    GET    {base}/api/sources?channel_id=<id>")
    print(f"    POST   {base}/api/sources")
    print(f"    DELETE {base}/api/sources/<id>")
    print()
    
    if config.auth.enabled:
        print("  🔒 Mutating endpoints (POST/PUT/PATCH/DELETE) require X-API-Key header")
        print()


def print_examples():
    """Print usage examples."""
    auth_header = ""
    if config.auth.enabled:
        auth_header = '\n       -H "X-API-Key: <your-api-key>" \\'
    
    print("📝 Examples:")
    print()
    print("  # Create a playlist")
    print(f'  curl -X POST http://localhost:5000/api/playlists \\')
    print(f'       -H "Content-Type: application/json" \\{auth_header}')
    print(f'       -d \'{{"name": "My IPTV", "epg_url": "http://example.com/epg.xml"}}\'')
    print()
    print("  # Add a channel")
    print(f'  curl -X POST http://localhost:5000/api/channels \\')
    print(f'       -H "Content-Type: application/json" \\{auth_header}')
    print(f'       -d \'{{"name": "CNN", "url": "http://example.com/cnn.m3u8", "playlist_id": "<id>"}}\'')
    print()
    print("  # Bulk create channels")
    print(f'  curl -X POST http://localhost:5000/api/channels/bulk \\')
    print(f'       -H "Content-Type: application/json" \\{auth_header}')
    print(f'       -d \'{{"playlist_id": "<id>", "channels": [{{"name": "CNN", "url": "..."}}]}}\'')
    print()
    print("  # Search channels")
    print('  curl "http://localhost:5000/api/channels/search?q=news"')
    print()
    print("  # Export playlist as M3U")
    print('  curl "http://localhost:5000/api/playlists/<id>/export" > playlist.m3u')
    print()


def main():
    """Main entry point."""
    print_banner()
    print_config()
    print_endpoints()
    print_examples()
    
    print("=" * 70)
    
    # Create app
    app = create_app()
    
    # Try Waitress for production, fall back to Flask dev server
    try:
        from waitress import serve
        print(f"🚀 Starting Waitress server on http://{config.server.host}:{config.server.port}")
        print("Press Ctrl+C to stop")
        print("=" * 70)
        print()
        serve(
            app,
            host=config.server.host,
            port=config.server.port,
            threads=4,
        )
    except ImportError:
        print("⚠️  Waitress not installed, using Flask development server")
        print(f"🚀 Starting server on http://{config.server.host}:{config.server.port}")
        print("Press Ctrl+C to stop")
        print("=" * 70)
        print()
        try:
            app.run(
                host=config.server.host,
                port=config.server.port,
                debug=config.server.debug,
                threaded=True,
                use_reloader=False,
            )
        except KeyboardInterrupt:
            print("\n\n🛑 Shutting down...")
            print("✅ Server stopped.")


if __name__ == '__main__':
    main()