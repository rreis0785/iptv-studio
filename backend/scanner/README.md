# Media Scanner Module

Scan websites and platforms for media content to add to IPTV playlists.

## Supported Platforms

- **YouTube**: Videos, playlists, channels, live streams, shorts
- **Twitch**: Live streams, VODs, clips, channels
- **Vimeo**: Videos, channels, user profiles
- **Generic Websites**: Auto-detect video files, HLS/DASH streams, embedded players

## Features

- Automatic platform detection
- Multiple quality stream extraction
- Live stream and VOD support
- Metadata extraction (title, description, thumbnails, duration)
- Direct conversion to IPTV channel/VOD format
- Batch scanning
- Rate limiting and retry logic

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### Python API

```python
import asyncio
from scanner import MediaScanner

async def main():
    scanner = MediaScanner()
    
    # Scan a YouTube channel
    result = await scanner.scan("https://youtube.com/@channel")
    
    print(f"Found {result.item_count} items")
    for item in result.items:
        print(f"  {item.title}: {item.stream_url}")
    
    # Convert to IPTV format
    channels = result.to_channels(playlist_id="abc123")
    vod = result.to_vod(playlist_id="abc123")

asyncio.run(main())
```

### REST API

```bash
# Scan a URL
curl -X POST http://localhost:5000/api/scanner/scan \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/@channel"}'

# Detect platform
curl "http://localhost:5000/api/scanner/detect?url=https://youtube.com/watch?v=abc"

# Import to playlist
curl -X POST http://localhost:5000/api/scanner/import \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://youtube.com/@channel",
    "playlist_id": "abc123",
    "import_live": true,
    "import_vod": true
  }'
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scanner/scan` | Scan a URL for media |
| POST | `/api/scanner/scan/batch` | Scan multiple URLs |
| GET/POST | `/api/scanner/probe` | Probe URL without extraction |
| GET | `/api/scanner/detect` | Detect platform for URL |
| GET | `/api/scanner/platforms` | List supported platforms |
| POST | `/api/scanner/import` | Scan and import to playlist |

## Data Models

### MediaItem

```json
{
  "id": "abc123",
  "title": "Video Title",
  "url": "https://youtube.com/watch?v=abc",
  "stream_url": "https://manifest.googlevideo.com/...",
  "media_type": "vod",
  "platform": "youtube",
  "thumbnail_url": "https://i.ytimg.com/...",
  "duration": 300,
  "channel_name": "Channel Name",
  "is_live": false,
  "streams": [
    {
      "url": "...",
      "quality": "1080p",
      "protocol": "hls"
    }
  ]
}
```

### ScanResult

```json
{
  "id": "scan123",
  "url": "https://youtube.com/@channel",
  "platform": "youtube",
  "status": "completed",
  "item_count": 25,
  "live_count": 1,
  "vod_count": 24,
  "items": [...]
}
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `YOUTUBE_API_KEY` | - | YouTube Data API key (optional) |
| `TWITCH_CLIENT_ID` | - | Twitch API client ID |
| `TWITCH_CLIENT_SECRET` | - | Twitch API client secret |
| `HTTP_PROXY` | - | HTTP proxy URL |

## Project Structure

```
scanner/
├── __init__.py
├── config.py
├── models.py
├── scanner.py
├── http_client.py
├── routes.py
├── extractors/
│   ├── __init__.py
│   ├── base.py
│   ├── youtube.py
│   ├── twitch.py
│   ├── vimeo.py
│   └── generic.py
├── requirements.txt
└── README.md
```

## Adding New Extractors

1. Create a new file in `extractors/`
2. Subclass `BaseExtractor`
3. Define `PLATFORM` and `URL_PATTERNS`
4. Implement `extract()` method
5. Use `@register_extractor` decorator

```python
from scanner.extractors.base import BaseExtractor, register_extractor
from scanner.models import Platform

@register_extractor
class MyExtractor(BaseExtractor):
    PLATFORM = Platform.UNKNOWN
    URL_PATTERNS = [
        re.compile(r'mysite\.com/video/(\d+)'),
    ]
    
    async def extract(self, request):
        result = self._create_result(request)
        # ... extraction logic
        return result
```

## License

MIT