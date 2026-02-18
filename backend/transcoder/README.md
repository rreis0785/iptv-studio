# IPTV Transcoding Backend Server

Real-time video transcoding using FFmpeg with HLS output for browser-compatible multi-client streaming.

## Features

- **HLS Output**: Browser-compatible streaming via `.m3u8` playlists and `.ts` segments
- **Multi-Client Support**: Any number of clients can watch the same stream simultaneously
- **Smart Transcoding**: Copies H.264 video streams (no re-encoding), only transcodes audio to AAC
- **Auto-Restart**: Automatic retry with backoff when FFmpeg processes die
- **Multiple Concurrent Streams**: Thread-safe management of multiple streams
- **Automatic Cleanup**: Dead, idle, and orphaned streams/segments are cleaned up automatically
- **Stream Probing**: Detect codecs before starting transcoding
- **Resource Limits**: Configurable limits on concurrent streams and per-IP connections
- **API Key Auth**: Optional authentication for destructive endpoints
- **Production Server**: Waitress WSGI server support (auto-detected)
- **Health Monitoring**: Health check and statistics endpoints

## Requirements

- Python 3.9+
- FFmpeg (with ffprobe)
- Flask

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Verify FFmpeg is installed
ffmpeg -version
```

## Quick Start

```bash
# Run the server
python -m transcoder

# Or use the entry point directly
python transcoder/__main__.py
```

## Configuration

Configuration can be set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `5000` | Server port |
| `DEBUG` | `false` | Enable debug mode |
| `LOG_LEVEL` | `INFO` | Logging level |
| `FFMPEG_PATH` | `ffmpeg` | Path to FFmpeg binary |
| `FFMPEG_PRESET` | `ultrafast` | FFmpeg encoding preset |
| `FFMPEG_CRF` | `28` | FFmpeg CRF value |
| `FFMPEG_MAX_RETRIES` | `3` | Max auto-restart attempts |
| `FFMPEG_RETRY_DELAY` | `2.0` | Seconds between retries |
| `AUDIO_BITRATE` | `192k` | Audio bitrate |
| `MAX_CONCURRENT_STREAMS` | `10` | Maximum concurrent streams |
| `STREAM_IDLE_TIMEOUT` | `300` | Idle timeout in seconds |
| `HLS_SEGMENT_DURATION` | `6` | HLS segment length in seconds |
| `HLS_PLAYLIST_SIZE` | `5` | Number of segments in playlist |
| `HLS_SEGMENT_DIR` | `<tempdir>/iptv-transcoder-hls` | HLS segment storage directory |
| `API_KEY` | *(none)* | API key for protected endpoints |

## Authentication

Set the `API_KEY` environment variable to enable authentication:

```bash
API_KEY=my-secret-key python -m transcoder
```

When enabled, destructive endpoints (`POST /api/stream`, `DELETE /api/stream/<id>`, `POST /api/streams/stop-all`) require the `X-API-Key` header. Read-only endpoints remain open.

## API Endpoints

### Health & Status

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/health` | No | Server health check |
| `GET` | `/api/stats` | No | Server statistics |

### Stream Management

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/stream?url=<URL>` | No | Create/get stream, returns HLS info |
| `POST` | `/api/stream` | 🔒 | Create stream (JSON body) |
| `GET` | `/api/stream/<id>` | No | Get stream info |
| `GET` | `/api/stream/<id>/status` | No | Detailed stream status |
| `DELETE` | `/api/stream/<id>` | 🔒 | Stop and remove stream |
| `GET` | `/api/streams` | No | List all active streams |
| `POST` | `/api/streams/stop-all` | 🔒 | Stop all streams |

### HLS Streaming

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/stream/<id>/playlist.m3u8` | No | HLS playlist (point player here) |
| `GET` | `/api/stream/<id>/segments/<file>` | No | HLS segment file |

### Probing

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET/POST` | `/api/probe?url=<URL>` | No | Probe stream codecs |

## HLS Streaming Guide

### 1. Create a stream

```bash
curl 'http://localhost:5000/api/stream?url=http://example.com/live.ts'
```

Response:
```json
{
  "success": true,
  "stream_id": "stream_1234567890_0001",
  "hls_url": "/api/stream/stream_1234567890_0001/playlist.m3u8"
}
```

### 2. Play in browser

Use [hls.js](https://github.com/video-dev/hls.js/) or a similar HLS player:

```html
<script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
<video id="video"></video>
<script>
  const video = document.getElementById('video');
  if (Hls.isSupported()) {
    const hls = new Hls();
    hls.loadSource('http://localhost:5000/api/stream/stream_1234567890_0001/playlist.m3u8');
    hls.attachMedia(video);
  }
</script>
```

Safari supports HLS natively:
```html
<video src="http://localhost:5000/api/stream/stream_1234567890_0001/playlist.m3u8"></video>
```

## Production Deployment

### Using Waitress (recommended)

Waitress is auto-detected. Install it:

```bash
pip install waitress
python -m transcoder
```

The server will automatically use Waitress instead of Flask's dev server.

### Using Gunicorn (Linux/macOS)

```bash
pip install gunicorn
gunicorn "transcoder.app:create_app()" -w 4 --threads 12 -b 0.0.0.0:5000
```

## Project Structure

```
transcoder/
├── __init__.py      # Package exports
├── __main__.py      # Entry point (Waitress/Flask)
├── app.py           # Flask app factory
├── config.py        # Configuration (FFmpeg, HLS, Auth, etc.)
├── exceptions.py    # Custom exceptions
├── manager.py       # Stream manager (lifecycle, cleanup)
├── models.py        # Data models (StreamInfo, CodecInfo, etc.)
├── routes.py        # API routes (REST + HLS serving)
├── transcoder.py    # FFmpeg transcoder (HLS output, auto-restart)
├── utils.py         # Utility functions
├── requirements.txt # Dependencies
└── README.md        # Documentation
```

## License

MIT