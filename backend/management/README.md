# IPTV Playlist Management Backend

Production-ready backend for managing IPTV playlists, channels, EPG, and VOD.

## Features

- **Store**: JSON file persistence with atomic writes (default) or in-memory mode
- **Playlists**: Import/Export (M3U/M3U8, JSON, XML) with auto-detection
- **Channels**: Live stream management with full M3U attribute support
- **VOD**: Video on Demand with watch progress tracking & metadata
- **Groups**: Organize content into categories
- **EPG**: Electronic Program Guide with scheduling
- **Series**: TV series with episode management
- **Security**: API Key authentication for write operations
- **Performance**: Bull operations for high-volume updates

## Requirements

- Python 3.9+
- Flask
- Waitress (Production server)

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Configure the application via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY` | Protects mutating endpoints (POST/PUT/DELETE) | None (Auth disabled) |
| `DATA_DIR` | Directory for JSON file storage | `./data` |
| `STORAGE_BACKEND` | Storage type: `json` (persistent) or `memory` (ephemeral) | `json` |
| `FLASK_ENV` | `production` or `development` | `production` |

## Quick Start

```bash
# Run with default settings (JSON storage in ./data)
python -m management

# Run with custom data directory and authentication enabled
# Linux/Mac
API_KEY=secret123 DATA_DIR=/var/lib/iptv python -m management

# Windows (PowerShell)
$env:API_KEY="secret123"; $env:DATA_DIR="C:\iptv-data"; python -m management
```

## API Endpoints

**Authentication**: If `API_KEY` is set, all POST/PUT/PATCH/DELETE requests require header `X-API-Key: <your-key>`.

### Health & Stats

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/stats` | Storage statistics (counts per entity type) |

### Playlists

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/playlists` | List all playlists |
| POST | `/api/playlists` | Create playlist |
| GET | `/api/playlists/{id}` | Get playlist |
| PUT | `/api/playlists/{id}` | Update playlist |
| DELETE | `/api/playlists/{id}` | Delete playlist |
| POST | `/api/playlists/import` | **Import playlist** (File/Raw) - Auto-detects M3U/JSON/XML |
| GET | `/api/playlists/{id}/export` | **Export playlist** (`?format=m3u|json|xml`) |
| POST | `/api/playlists/{id}/default` | Set as default |
| GET | `/api/playlists/{id}/channels` | List channels in playlist |
| GET | `/api/playlists/{id}/vod` | List VOD in playlist |
| GET | `/api/playlists/{id}/groups` | List groups in playlist |

### Channels (Live Streams)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/channels` | List channels |
| POST | `/api/channels` | Create channel |
| POST | `/api/channels/bulk` | **Bulk create channels** |
| POST | `/api/channels/bulk-update` | **Bulk update channels** |
| GET | `/api/channels/{id}` | Get channel |
| PUT | `/api/channels/{id}` | Update channel |
| DELETE | `/api/channels/{id}` | Delete channel |
| GET | `/api/channels/search?q={query}` | Search channels |
| GET | `/api/channels/favorites` | Get favorites |
| POST | `/api/channels/{id}/favorite` | Toggle favorite |
| POST | `/api/channels/reorder` | Reorder channels |
| POST | `/api/channels/move` | Move to group |
| GET | `/api/channels/{id}/epg` | Get EPG |
| GET | `/api/channels/{id}/sources` | Get sources |

### VOD (Video on Demand)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/vod` | List VOD |
| POST | `/api/vod` | Create VOD |
| POST | `/api/vod/bulk` | **Bulk create VOD** |
| POST | `/api/vod/bulk-update` | **Bulk update VOD** |
| GET | `/api/vod/{id}` | Get VOD |
| PUT | `/api/vod/{id}` | Update VOD |
| DELETE | `/api/vod/{id}` | Delete VOD |
| GET | `/api/vod/search?q={query}` | Search VOD |
| GET | `/api/vod/continue-watching` | In-progress items |
| GET | `/api/vod/recently-watched` | Recent items |
| POST | `/api/vod/{id}/progress` | Update progress |
| POST | `/api/vod/{id}/favorite` | Toggle favorite |

### Groups

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/groups` | List groups |
| POST | `/api/groups` | Create group |
| POST | `/api/groups/bulk` | **Bulk create groups** |
| GET | `/api/groups/{id}` | Get group |
| PUT | `/api/groups/{id}` | Update group |
| DELETE | `/api/groups/{id}` | Delete group |
| POST | `/api/groups/reorder` | Reorder groups |
| POST | `/api/groups/merge` | Merge groups |
| GET | `/api/groups/{id}/channels` | Get channels in group |
| GET | `/api/groups/{id}/vod` | Get VOD in group |

### EPG (Program Guide)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/epg?channel_id={id}` | List programs |
| POST | `/api/epg` | Create program |
| POST | `/api/epg/bulk` | Bulk create programs |
| GET | `/api/epg/current?channel_id={id}` | Current programs |
| GET | `/api/epg/schedule/{channel_id}` | Day schedule |
| DELETE | `/api/epg/channel/{id}/clear` | Clear channel EPG |
| POST | `/api/epg/cleanup` | Clean old data |

### Series

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/series` | List series |
| POST | `/api/series` | Create series |
| GET | `/api/series/{id}` | Get series |
| PUT | `/api/series/{id}` | Update series |
| DELETE | `/api/series/{id}` | Delete series |
| GET | `/api/series/search?q={query}` | Search series |
| GET | `/api/series/{id}/episodes` | Get episodes |
| POST | `/api/series/{id}/episodes` | Add episode |
| GET | `/api/series/{id}/seasons` | Get seasons |

### Stream Sources

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sources?channel_id={id}` | List sources |
| POST | `/api/sources` | Create source |
| GET | `/api/sources/{id}` | Get source |
| PUT | `/api/sources/{id}` | Update source |
| DELETE | `/api/sources/{id}` | Delete source |
| POST | `/api/sources/{id}/primary` | Set primary |

## Data Models

### Playlist
```json
{
  "id": "abc123",
  "name": "My IPTV",
  "description": "My playlist",
  "url": "http://example.com/playlist.m3u",
  "epg_url": "http://example.com/epg.xml",
  "channel_count": 100,
  "vod_count": 50,
  "group_count": 10,
  "is_active": true,
  "is_default": true
}
```

### Channel
```json
{
  "id": "ch123",
  "name": "CNN",
  "url": "http://example.com/cnn.m3u8",
  "playlist_id": "abc123",
  "group_id": "grp1",
  "tvg_id": "cnn.us",
  "tvg_name": "CNN HD",
  "logo_url": "http://example.com/cnn.png",
  "channel_number": 1,
  "catchup_type": "default",
  "catchup_days": 7,
  "is_favorite": false,
  "is_hidden": false
}
```

## Project Structure

```
management/
├── __init__.py
├── __main__.py       # Entry point
├── app.py            # App factory
├── config.py         # Configuration & Auth
├── models.py         # Data models
├── storage.py        # JSON & Memory persistence
├── services.py       # Business logic
├── validators.py     # Input validation
├── parsers.py        # M3U/JSON/XML Parsers
├── exporters.py      # M3U/JSON/XML Exporters
├── routes/           # API Endpoints
│   ├── playlists.py
│   ├── channels.py
│   ├── vod.py
│   ├── groups.py
│   ├── epg.py
│   ├── series.py
│   └── sources.py
└── requirements.txt
```

## License

MIT