# Media Scanner Module

Scan websites and platforms for media content to add to IPTV playlists.

## Table of Contents

- [Module Overview](#module-overview)
- [Supported Sources](#supported-sources)
- [Usage Examples](#usage-examples)
- [Module Reference](#module-reference)
  - [scanner (`__init__.py`)](#scanner-__init__py)
  - [config.py](#configpy)
  - [http_client.py](#http_clientpy)
  - [models.py](#modelspy)
  - [scanner.py](#scannerpy)
  - [routes.py](#routespy)
  - [extractors/](#extractors)
    - [extractors/__init__.py](#extractors__init__py)
    - [extractors/base.py](#extractorsbasepy)
    - [extractors/generic.py](#extractorsgenericpy)
    - [extractors/playlist.py](#extractorsplaylistpy)
    - [extractors/twitch.py](#extractorstwitchpy)
    - [extractors/vimeo.py](#extractorsvimeopy)
    - [extractors/youtube.py](#extractorsyoutubepy)
- [Configuration Reference](#configuration-reference)
- [API Endpoint Reference](#api-endpoint-reference)
- [Data Model Reference](#data-model-reference)
- [Platform Support Details](#platform-support-details)
- [Project Structure](#project-structure)

---

## Module Overview

The `scanner` package discovers media content from a wide variety of sources and converts
the results to IPTV channel or VOD entries. It provides both a Python async API and a
Flask REST API.

## Supported Sources

- **YouTube** — channels, playlists, individual videos, live streams, Shorts
- **Twitch** — live channels, VODs (past broadcasts), clips
- **Vimeo** — individual videos, user profiles, channels, showcases
- **Dailymotion** — channels and videos (via generic scraper)
- **Direct M3U8 / MP4 links**
- **Generic website scraping** — `<video>` tags, `<iframe>` embeds, HLS/DASH URLs in scripts, JSON-LD structured data
- **RSS / Atom feeds** with media enclosures
- **Playlist files** — M3U, M3U8, PLS

---

## Usage Examples

### Python API (from `__init__.py` and `scanner.py` docstrings)

```python
from scanner import MediaScanner

scanner = MediaScanner()

# Scan a YouTube channel
results = await scanner.scan("https://youtube.com/@channel")

# Scan a website for streams
results = await scanner.scan("https://example.com/live")

# Convert to IPTV channels
channels = results.to_channels(playlist_id="abc123")
```

```python
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
```

### Convenience function (from `scanner.py`)

```python
result = await scan_url("https://youtube.com/@channel")
for item in result.items:
    print(f"{item.title}: {item.stream_url}")
```

---

## Module Reference

### scanner (`__init__.py`)

Top-level package init. Re-exports the primary public API.

**Exports:**

| Symbol | Source |
|---|---|
| `MediaScanner` | `scanner.scanner` |
| `ScanResult` | `scanner.models` |
| `MediaItem` | `scanner.models` |
| `MediaType` | `scanner.models` |
| `StreamQuality` | `scanner.models` |
| `ScanStatus` | `scanner.models` |
| `BaseExtractor` | `scanner.extractors` |
| `YouTubeExtractor` | `scanner.extractors` |
| `TwitchExtractor` | `scanner.extractors` |
| `VimeoExtractor` | `scanner.extractors` |
| `GenericExtractor` | `scanner.extractors` |

`__version__ = '1.0.0'`

---

### config.py

Scanner configuration settings. Provides dataclass-based configuration with environment variable support for all sensitive or deployment-specific values.

#### `NetworkConfig`

Network and HTTP settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `timeout` | `int` | `30` | Request timeout in seconds |
| `max_retries` | `int` | `3` | Maximum number of retry attempts |
| `retry_delay` | `float` | `1.0` | Base delay between retries (seconds) |
| `requests_per_second` | `float` | `2.0` | Rate limit — max requests per second |
| `user_agents` | `List[str]` | See below | Rotating list of User-Agent strings |
| `proxies` | `List[str]` | `[]` | Proxy URL pool |
| `proxy_file` | `Optional[str]` | `$PROXY_FILE` | Path to file containing proxy list |

Default user agent pool contains three Chrome 120 strings (Windows, macOS, Linux).

**`__post_init__` proxy loading logic:**

1. If `proxies` is empty, reads `HTTP_PROXY` env var.
2. Reads `HTTPS_PROXY` env var (deduplicates against `HTTP_PROXY`).
3. Reads `PROXY_LIST` env var (comma-separated list).
4. Reads from `proxy_file` if set and the file exists; lines starting with `#` are skipped.
   Logs a warning at `WARNING` level on file read failure.

#### `YouTubeConfig`

YouTube-specific settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `api_key` | `Optional[str]` | `$YOUTUBE_API_KEY` | YouTube Data API key (optional; for higher rate limits) |
| `max_videos_per_channel` | `int` | `50` | Max videos to fetch per channel scan |
| `max_playlist_items` | `int` | `100` | Max items to fetch per playlist scan |
| `include_shorts` | `bool` | `False` | Whether to include YouTube Shorts |
| `include_live_only` | `bool` | `False` | Fetch live streams only |
| `preferred_quality` | `str` | `'best'` | Quality preference: `best`, `1080p`, `720p`, `480p`, `worst` |
| `prefer_hls` | `bool` | `True` | Prefer HLS streams over progressive |

#### `TwitchConfig`

Twitch-specific settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `client_id` | `Optional[str]` | `$TWITCH_CLIENT_ID` | Twitch API client ID |
| `client_secret` | `Optional[str]` | `$TWITCH_CLIENT_SECRET` | Twitch API client secret |
| `include_vods` | `bool` | `True` | Include past broadcast VODs |
| `include_clips` | `bool` | `False` | Include channel clips |
| `max_vods` | `int` | `20` | Maximum VODs to fetch per channel |

#### `ScraperConfig`

Generic scraper settings.

| Field | Type | Default | Description |
|---|---|---|---|
| `follow_links` | `bool` | `True` | Follow links on scraped pages |
| `max_depth` | `int` | `2` | Maximum crawl depth |
| `max_pages` | `int` | `10` | Maximum pages to visit |
| `detect_m3u8` | `bool` | `True` | Detect HLS manifest URLs |
| `detect_mp4` | `bool` | `True` | Detect MP4 direct links |
| `detect_embedded_players` | `bool` | `True` | Detect embedded video players |
| `detect_iframes` | `bool` | `True` | Detect iframe video embeds |
| `min_duration` | `int` | `0` | Minimum media duration in seconds (0 = no minimum) |
| `max_duration` | `int` | `0` | Maximum media duration in seconds (0 = no maximum) |
| `use_browser` | `bool` | `False` | Use Playwright for JS rendering (requires playwright) |
| `browser_timeout` | `int` | `30000` | Browser operation timeout in milliseconds |
| `wait_for_network_idle` | `bool` | `True` | Wait for network idle before extracting |

#### `ScannerConfig`

Main scanner configuration. Aggregates all sub-configs.

| Field | Type | Default | Description |
|---|---|---|---|
| `network` | `NetworkConfig` | `NetworkConfig()` | Network/HTTP settings |
| `youtube` | `YouTubeConfig` | `YouTubeConfig()` | YouTube-specific settings |
| `twitch` | `TwitchConfig` | `TwitchConfig()` | Twitch-specific settings |
| `scraper` | `ScraperConfig` | `ScraperConfig()` | Generic scraper settings |
| `cache_enabled` | `bool` | `True` | Enable response caching |
| `cache_ttl` | `int` | `3600` | Cache time-to-live in seconds |
| `auto_generate_thumbnails` | `bool` | `False` | Auto-generate thumbnails |
| `extract_metadata` | `bool` | `True` | Extract media metadata |

A module-level `config = ScannerConfig()` instance is provided as the default global configuration.

---

### http_client.py

Async HTTP client for the media scanner. Provides a unified interface for making HTTP requests with:
- Automatic retries
- Rate limiting
- User agent rotation
- Proxy support
- Response caching

#### `HttpResponse`

HTTP response wrapper dataclass.

| Field | Type | Default |
|---|---|---|
| `url` | `str` | required |
| `status_code` | `int` | required |
| `headers` | `Dict[str, str]` | `{}` |
| `text` | `str` | `""` |
| `content` | `bytes` | `b""` |

**Properties:**

- `success` — Returns `True` if `200 <= status_code < 400`.
- `is_redirect` — Returns `True` if `300 <= status_code < 400`.

**Methods:**

- `json()` — Parses `self.text` as JSON and returns the result.

#### `HttpClient`

Async HTTP client with advanced features:
- Automatic retries with exponential backoff
- Rate limiting per domain
- User agent rotation
- Response caching
- Cookie persistence

**Class attribute:**

`DEFAULT_USER_AGENTS` — List of four browser User-Agent strings (Chrome 120 on Windows/macOS/Linux, Firefox 121 on Windows).

**Constructor parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `timeout` | `int` | `30` | Request timeout in seconds |
| `max_retries` | `int` | `3` | Max retry attempts |
| `retry_delay` | `float` | `1.0` | Base retry delay in seconds |
| `requests_per_second` | `float` | `2.0` | Max requests per second per domain |
| `user_agents` | `List[str]` | `None` | Custom UA list; falls back to `DEFAULT_USER_AGENTS` |
| `proxies` | `List[str]` | `None` | Proxy pool; falls back to `config.network.proxies` |

**Public methods:**

- `async get(url, headers=None, params=None, allow_redirects=True)` — Make a GET request. Returns `HttpResponse`.
- `async post(url, headers=None, data=None, json=None)` — Make a POST request. Returns `HttpResponse`.
- `async close()` — Close the underlying aiohttp `ClientSession`.

**Internal methods:**

- `async _get_session()` — Lazy-initialises and returns an `aiohttp.ClientSession`. Logs a debug message if `aiohttp` is unavailable.
- `async _rate_limit(domain)` — Applies per-domain rate limiting using a monotonic clock and `asyncio.Lock`.
- `_get_headers(headers=None)` — Builds request headers, merging defaults (random UA, Accept, DNT, etc.) with any caller-supplied headers.
- `_get_proxy()` — Returns the next proxy from the round-robin cycle, or `None` if no proxies are configured.
- `async _request(method, url, ...)` — Core request dispatcher; applies rate limiting, builds headers, retries on 5xx or exceptions with exponential backoff (`delay = retry_delay * 2^attempt`). Returns a status-0 `HttpResponse` on exhaustion.
- `async _do_request(method, url, ...)` — Executes the actual request via the shared `aiohttp` session, or falls back to `_urllib_request` if `aiohttp` is unavailable.
- `async _urllib_request(method, url, ...)` — Synchronous urllib fallback executed in a thread-pool executor. Handles `HTTPError` by returning the error response body.

A module-level `http_client = HttpClient()` instance is provided as the global default client.

---

### models.py

Data models for the media scanner.

#### Helper functions

- `generate_id() -> str` — Generates a 12-character hex UUID fragment (unique identifier for model instances).
- `utcnow() -> datetime` — Returns the current UTC datetime.

#### Enums

##### `MediaType(str, Enum)`

Type of media content.

| Value | Meaning |
|---|---|
| `LIVE` | `"live"` |
| `VOD` | `"vod"` |
| `PLAYLIST` | `"playlist"` |
| `CHANNEL` | `"channel"` |
| `CLIP` | `"clip"` |
| `SHORT` | `"short"` |
| `UNKNOWN` | `"unknown"` |

##### `StreamQuality(str, Enum)`

Stream quality levels.

| Value | Meaning |
|---|---|
| `QUALITY_4K` | `"4k"` |
| `QUALITY_1440P` | `"1440p"` |
| `QUALITY_1080P` | `"1080p"` |
| `QUALITY_720P` | `"720p"` |
| `QUALITY_480P` | `"480p"` |
| `QUALITY_360P` | `"360p"` |
| `QUALITY_240P` | `"240p"` |
| `AUDIO_ONLY` | `"audio"` |
| `UNKNOWN` | `"unknown"` |

##### `Platform(str, Enum)`

Source platform.

| Value | String |
|---|---|
| `YOUTUBE` | `"youtube"` |
| `TWITCH` | `"twitch"` |
| `VIMEO` | `"vimeo"` |
| `DAILYMOTION` | `"dailymotion"` |
| `FACEBOOK` | `"facebook"` |
| `TWITTER` | `"twitter"` |
| `INSTAGRAM` | `"instagram"` |
| `TIKTOK` | `"tiktok"` |
| `RUMBLE` | `"rumble"` |
| `KICK` | `"kick"` |
| `DIRECT` | `"direct"` |
| `WEBSITE` | `"website"` |
| `RSS` | `"rss"` |
| `UNKNOWN` | `"unknown"` |

##### `ScanStatus(str, Enum)`

Scan operation status.

| Value | Meaning |
|---|---|
| `PENDING` | `"pending"` |
| `SCANNING` | `"scanning"` |
| `COMPLETED` | `"completed"` |
| `PARTIAL` | `"partial"` |
| `FAILED` | `"failed"` |
| `CANCELLED` | `"cancelled"` |

##### `StreamProtocol(str, Enum)`

Stream protocol type.

| Value | String |
|---|---|
| `HLS` | `"hls"` |
| `DASH` | `"dash"` |
| `RTMP` | `"rtmp"` |
| `RTSP` | `"rtsp"` |
| `HTTP` | `"http"` |
| `PROGRESSIVE` | `"progressive"` |
| `UNKNOWN` | `"unknown"` |

#### `StreamInfo`

Dataclass describing a specific stream/quality variant.

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | required | Stream URL |
| `quality` | `StreamQuality` | `UNKNOWN` | Quality level |
| `protocol` | `StreamProtocol` | `UNKNOWN` | Stream protocol |
| `resolution` | `Optional[str]` | `None` | E.g. `"1920x1080"` |
| `width` | `Optional[int]` | `None` | Width in pixels |
| `height` | `Optional[int]` | `None` | Height in pixels |
| `bitrate` | `Optional[int]` | `None` | Bitrate in kbps |
| `fps` | `Optional[float]` | `None` | Frames per second |
| `video_codec` | `Optional[str]` | `None` | Video codec string |
| `audio_codec` | `Optional[str]` | `None` | Audio codec string |
| `headers` | `Dict[str, str]` | `{}` | HTTP headers required for playback |
| `user_agent` | `Optional[str]` | `None` | Required User-Agent for playback |
| `referrer` | `Optional[str]` | `None` | Required Referer header for playback |
| `is_drm_protected` | `bool` | `False` | Whether stream is DRM-protected |
| `drm_type` | `Optional[str]` | `None` | DRM type string |
| `expires_at` | `Optional[datetime]` | `None` | Expiry time of the stream URL |
| `is_temporary` | `bool` | `False` | Whether URL is temporary/signed |

**Methods:**

- `to_dict()` — Converts to dictionary; `quality` and `protocol` are serialized as their `.value` strings; `expires_at` is ISO-formatted if present.

#### `MediaItem`

A discovered media item (video, stream, channel). Represents a single piece of media content that can be converted to an IPTV channel or VOD entry.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `str` | `generate_id()` | Unique identifier (12-char hex) |
| `title` | `str` | `""` | Display title |
| `description` | `Optional[str]` | `None` | Description text |
| `url` | `str` | `""` | Original page URL |
| `media_type` | `MediaType` | `UNKNOWN` | Type of media content |
| `platform` | `Platform` | `UNKNOWN` | Source platform |
| `streams` | `List[StreamInfo]` | `[]` | Available stream variants |
| `stream_url` | `Optional[str]` | `None` | Primary/best stream URL for direct use |
| `thumbnail_url` | `Optional[str]` | `None` | Thumbnail image URL |
| `logo_url` | `Optional[str]` | `None` | Logo image URL |
| `channel_name` | `Optional[str]` | `None` | Channel/author name |
| `channel_id` | `Optional[str]` | `None` | Channel/author ID |
| `channel_url` | `Optional[str]` | `None` | Channel page URL |
| `channel_logo` | `Optional[str]` | `None` | Channel logo URL |
| `duration` | `Optional[int]` | `None` | Duration in seconds |
| `view_count` | `Optional[int]` | `None` | View count |
| `like_count` | `Optional[int]` | `None` | Like count |
| `upload_date` | `Optional[datetime]` | `None` | Upload date |
| `category` | `Optional[str]` | `None` | Category/genre string |
| `tags` | `List[str]` | `[]` | Tag list |
| `is_live` | `bool` | `False` | Whether this is a live stream |
| `is_upcoming` | `bool` | `False` | Whether stream is scheduled (not yet live) |
| `scheduled_start` | `Optional[datetime]` | `None` | Scheduled start time |
| `viewer_count` | `Optional[int]` | `None` | Current live viewer count |
| `language` | `Optional[str]` | `None` | Content language code |
| `external_id` | `Optional[str]` | `None` | Platform-specific ID |
| `is_age_restricted` | `bool` | `False` | Age restriction flag |
| `extracted_at` | `datetime` | `utcnow()` | Extraction timestamp |
| `extractor` | `Optional[str]` | `None` | Name of the extractor class used |
| `raw_data` | `Optional[Dict[str, Any]]` | `None` | Raw platform data (excluded from repr) |

**Properties:**

- `best_stream` — Returns the highest-quality `StreamInfo` from `streams`, following the priority order: 4K > 1440p > 1080p > 720p > 480p > 360p > 240p. Falls back to `streams[0]`. Returns `None` if `streams` is empty.
- `duration_formatted` — Returns duration as `H:MM:SS` or `M:SS` string. Returns `None` if `duration` is not set.

**Methods:**

- `to_dict()` — Serializes to a dictionary for JSON output. Includes `duration_formatted`, all enum values as strings, and ISO-formatted dates.
- `to_channel_dict(playlist_id, group_id=None)` — Converts to IPTV channel creation format with fields: `name`, `url`, `playlist_id`, `group_id`, `logo_url`, `tvg_name`, `tvg_id`, `stream_type` (`"live"` or `"vod"`), `user_agent`, `referrer`, `http_headers`.
- `to_vod_dict(playlist_id, group_id=None)` — Converts to IPTV VOD creation format with fields: `name`, `url`, `playlist_id`, `group_id`, `content_type` (`"video"`), `duration`, `poster_url`, `plot`, `genre`, `user_agent`, `referrer`.

#### `ScanResult`

Result of a media scan operation. Contains all discovered media items and metadata about the scan.

| Field | Type | Default | Description |
|---|---|---|---|
| `id` | `str` | `generate_id()` | Unique scan identifier |
| `url` | `str` | `""` | Input URL |
| `platform` | `Platform` | `UNKNOWN` | Detected platform |
| `status` | `ScanStatus` | `PENDING` | Current scan status |
| `error_message` | `Optional[str]` | `None` | Error details on failure |
| `items` | `List[MediaItem]` | `[]` | Discovered media items |
| `total_count` | `int` | `0` | Total items available (may exceed `len(items)`) |
| `has_more` | `bool` | `False` | Indicates more items exist beyond current page |
| `next_page_token` | `Optional[str]` | `None` | Token for fetching the next page |
| `source_title` | `Optional[str]` | `None` | Title of the source (channel/playlist name) |
| `source_description` | `Optional[str]` | `None` | Description of the source |
| `source_thumbnail` | `Optional[str]` | `None` | Thumbnail of the source |
| `source_channel` | `Optional[str]` | `None` | Source channel name |
| `started_at` | `Optional[datetime]` | `None` | Scan start time |
| `completed_at` | `Optional[datetime]` | `None` | Scan completion time |
| `duration_ms` | `Optional[int]` | `None` | Total scan duration in milliseconds |
| `pages_scanned` | `int` | `0` | Number of pages visited |
| `requests_made` | `int` | `0` | Total HTTP requests made |

**Properties:**

- `item_count` — Number of items in `items`.
- `live_count` — Number of items where `is_live == True`.
- `vod_count` — Number of items where `is_live == False`.
- `is_success` — `True` if `status` is `COMPLETED` or `PARTIAL`.

**Methods:**

- `to_dict()` — Serializes to dictionary for JSON output.
- `to_channels(playlist_id, group_id=None)` — Returns list of channel dicts (via `MediaItem.to_channel_dict`) for all live items only.
- `to_vod(playlist_id, group_id=None)` — Returns list of VOD dicts (via `MediaItem.to_vod_dict`) for all non-live items only.
- `filter_live()` — Returns only live `MediaItem` objects.
- `filter_vod()` — Returns only non-live `MediaItem` objects.
- `filter_by_platform(platform)` — Returns `MediaItem` objects matching the given `Platform`.

#### `ScanRequest`

Request parameters for a scan operation.

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | required | URL to scan |
| `include_live` | `bool` | `True` | Include live streams in results |
| `include_vod` | `bool` | `True` | Include VOD content in results |
| `max_items` | `int` | `50` | Maximum items to return |
| `min_quality` | `Optional[StreamQuality]` | `None` | Minimum quality filter |
| `force_platform` | `Optional[Platform]` | `None` | Force a specific extractor platform |
| `page_token` | `Optional[str]` | `None` | Pagination token |
| `max_depth` | `int` | `2` | Maximum crawl depth for website scraping |
| `follow_links` | `bool` | `True` | Follow links during website scraping |
| `auth_token` | `Optional[str]` | `None` | Authentication token for supported platforms |
| `cookies` | `Dict[str, str]` | `{}` | Cookies for authenticated requests |

---

### scanner.py

Main media scanner class. Coordinates extractors to scan URLs and discover media content.

#### `MediaScanner`

Main scanner class for discovering media content. Automatically selects the appropriate extractor based on URL and coordinates the extraction process.

**Constructor:**

```python
MediaScanner(scanner_config: ScannerConfig = None)
```

- `scanner_config` — Optional custom `ScannerConfig`; defaults to the global `config` instance.

**Methods:**

- `async scan(url, include_live=True, include_vod=True, max_items=50, max_depth=2, follow_links=True) -> ScanResult` — Scan a URL for media content. Builds a `ScanRequest` and dispatches to `_scan()`.
- `async scan_many(urls, **kwargs) -> List[ScanResult]` — Scan multiple URLs concurrently using `asyncio.gather`. Returns results in the same order as input URLs. Accepts all keyword arguments that `scan()` accepts.
- `detect_platform(url) -> Platform` — Detect the platform for a URL without performing a scan. Delegates to `ExtractorRegistry.get_platform()`.
- `get_supported_platforms() -> List[Platform]` — Returns a list of `Platform` values for all registered extractor classes.
- `async probe_url(url) -> dict` — Probe a URL to get basic info without full extraction. Makes a GET request and returns `{'url', 'platform', 'extractor', 'accessible', 'status_code', 'content_type'}`.
- `async close()` — Close the scanner and release resources (closes the global `http_client`).
- `async __aenter__()` / `async __aexit__()` — Async context manager support; calls `close()` on exit.

**Internal methods:**

- `async _scan(request: ScanRequest) -> ScanResult` — Internal scan implementation. Selects extractor, runs `extractor.extract(request)`, applies live/VOD filters and `max_items` cap, and returns the result. Logs item counts on completion.
- `_get_extractor(url, force_platform=None) -> Optional[BaseExtractor]` — Returns an extractor instance for the given URL. If `force_platform` is set, finds the matching extractor by platform; otherwise delegates to the registry.

#### Module-level convenience function

```python
async def scan_url(url: str, **kwargs) -> ScanResult
```

Convenience function to scan a single URL. Creates a `MediaScanner`, scans the URL, closes the scanner, and returns the result.

```python
result = await scan_url("https://youtube.com/@channel")
for item in result.items:
    print(f"{item.title}: {item.stream_url}")
```

---

### routes.py

Flask API routes for the media scanner. Provides REST endpoints for scanning URLs and managing scan jobs.

The Blueprint is registered at the URL prefix `/api/scanner`.

#### Rate limiting

A simple in-process rate limiter is implemented using a module-level dictionary (`_rate_cache`) keyed by `"scan:{remote_addr}"`. All scan endpoints share a limit of **10 requests per minute per IP address**. Timestamps outside the rolling 60-second window are evicted on each check. The implementation is thread-safe via `threading.Lock`.

- `_is_rate_limited(key, max_requests, window_seconds) -> bool` — Core rate check. Returns `True` if the caller has exceeded the allowed rate.
- `_scan_rate_limit() -> bool` — Applies the per-IP scan rate limit (10 req/min).

#### Helper

- `run_async(coro)` — Runs an async coroutine in a synchronous Flask context by obtaining (or creating) an event loop.

---

## API Endpoint Reference

### `POST /api/scanner/scan`

Scan a URL for media content.

**Rate limit:** 10 requests per minute per IP (HTTP 429 on excess).

**Request body (JSON):**

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | `string` | required | URL to scan |
| `include_live` | `boolean` | `true` | Include live streams |
| `include_vod` | `boolean` | `true` | Include VOD content |
| `max_items` | `integer` | `50` | Max items (capped at 200 server-side) |
| `max_depth` | `integer` | `2` | Max crawl depth (capped at 5 server-side) |
| `follow_links` | `boolean` | `true` | Follow links on websites |

**Example request:**

```json
{
    "url": "https://youtube.com/@channel",
    "include_live": true,
    "include_vod": true,
    "max_items": 50,
    "max_depth": 2,
    "follow_links": true
}
```

**Response:** `ScanResult` JSON object (see [Data Model Reference](#data-model-reference)).

**Error responses:**

| Status | Condition |
|---|---|
| `400` | `url` field missing |
| `429` | Rate limit exceeded |
| `500` | Unexpected exception |

---

### `POST /api/scanner/scan/batch`

Scan multiple URLs.

**Rate limit:** 10 requests per minute per IP (HTTP 429 on excess).

**Request body (JSON):**

| Field | Type | Default | Description |
|---|---|---|---|
| `urls` | `array[string]` | required | List of URLs to scan (max 10) |
| `include_live` | `boolean` | `true` | Include live streams |
| `include_vod` | `boolean` | `true` | Include VOD content |
| `max_items` | `integer` | `20` | Max items per URL |

**Example request:**

```json
{
    "urls": [
        "https://youtube.com/@channel1",
        "https://twitch.tv/streamer"
    ],
    "include_live": true,
    "include_vod": true,
    "max_items": 20
}
```

**Response:**

```json
{
    "count": 2,
    "results": [ ... ]
}
```

**Error responses:**

| Status | Condition |
|---|---|
| `400` | `urls` array missing or empty |
| `400` | More than 10 URLs supplied |
| `429` | Rate limit exceeded |
| `500` | Unexpected exception |

---

### `GET /api/scanner/probe` or `POST /api/scanner/probe`

Probe a URL without full extraction.

**GET — Query parameters:**

| Parameter | Description |
|---|---|
| `url` | URL to probe |

**POST — Request body (JSON):**

| Field | Description |
|---|---|
| `url` | URL to probe |

**Response:** URL info including platform and accessibility.

```json
{
    "url": "https://example.com/live",
    "platform": "website",
    "extractor": "GenericExtractor",
    "accessible": true,
    "status_code": 200,
    "content_type": "text/html; charset=utf-8"
}
```

**Error responses:**

| Status | Condition |
|---|---|
| `400` | `url` parameter missing |
| `500` | Unexpected exception |

---

### `GET /api/scanner/platforms`

List all supported platforms.

**Response:**

```json
{
    "count": 5,
    "platforms": ["youtube", "twitch", "vimeo", "website", "playlist"]
}
```

---

### `GET /api/scanner/detect`

Detect the platform for a URL.

**Query parameters:**

| Parameter | Description |
|---|---|
| `url` | URL to analyze |

**Response:**

```json
{
    "url": "https://youtube.com/watch?v=abc",
    "platform": "youtube"
}
```

**Error responses:**

| Status | Condition |
|---|---|
| `400` | `url` parameter missing |

---

### `POST /api/scanner/import`

Scan a URL and import results into an IPTV playlist. If the `iptv.services` module is available, channels and VODs are created via `services.channels.create()` and `services.vod.create()`. If the module is not available, the endpoint still returns the data without persisting it.

**Request body (JSON):**

| Field | Type | Default | Description |
|---|---|---|---|
| `url` | `string` | required | URL to scan |
| `playlist_id` | `string` | required | Target playlist ID |
| `group_id` | `string` | `null` | Optional group ID |
| `import_live` | `boolean` | `true` | Import live channels |
| `import_vod` | `boolean` | `true` | Import VOD content |
| `max_items` | `integer` | `50` | Max items to import |

**Example request:**

```json
{
    "url": "https://youtube.com/@channel",
    "playlist_id": "abc123",
    "group_id": "def456",
    "import_live": true,
    "import_vod": true,
    "max_items": 50
}
```

**Response:**

```json
{
    "success": true,
    "scan_result": {
        "url": "https://youtube.com/@channel",
        "platform": "youtube",
        "items_found": 25
    },
    "imported": {
        "channels": 1,
        "vod": 24,
        "channel_ids": ["ch_abc"],
        "vod_ids": ["vod_1", "vod_2"]
    },
    "channels_data": [ ... ],
    "vod_data": [ ... ]
}
```

**Error responses:**

| Status | Condition |
|---|---|
| `400` | `url` or `playlist_id` missing |
| `400` | Scan failed (returns `error_message`) |
| `500` | Unexpected exception |

---

## Data Model Reference

### `MediaItem` JSON shape

```json
{
    "id": "abc123def456",
    "title": "Video Title",
    "description": "Optional description",
    "url": "https://youtube.com/watch?v=abc123",
    "media_type": "vod",
    "platform": "youtube",
    "stream_url": "https://manifest.googlevideo.com/...",
    "streams": [
        {
            "url": "https://...",
            "quality": "1080p",
            "protocol": "progressive",
            "resolution": "1920x1080",
            "width": 1920,
            "height": 1080,
            "bitrate": 4000,
            "fps": 30.0,
            "video_codec": "avc1",
            "audio_codec": null,
            "headers": {},
            "user_agent": null,
            "referrer": null,
            "is_drm_protected": false,
            "drm_type": null,
            "expires_at": null,
            "is_temporary": false
        }
    ],
    "thumbnail_url": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
    "logo_url": null,
    "channel_name": "Channel Name",
    "channel_id": "UC_abc123",
    "channel_url": "https://www.youtube.com/channel/UC_abc123",
    "duration": 300,
    "duration_formatted": "5:00",
    "view_count": 100000,
    "is_live": false,
    "is_upcoming": false,
    "category": "Entertainment",
    "tags": ["tag1", "tag2"],
    "language": null,
    "external_id": "abc123",
    "extracted_at": "2026-02-18T12:00:00"
}
```

### `ScanResult` JSON shape

```json
{
    "id": "scan123abc",
    "url": "https://youtube.com/@channel",
    "platform": "youtube",
    "status": "completed",
    "error_message": null,
    "item_count": 25,
    "live_count": 1,
    "vod_count": 24,
    "total_count": 25,
    "has_more": false,
    "source_title": "My YouTube Channel",
    "source_channel": "My YouTube Channel",
    "pages_scanned": 1,
    "requests_made": 3,
    "started_at": "2026-02-18T12:00:00",
    "completed_at": "2026-02-18T12:00:05",
    "duration_ms": 5000,
    "items": [ ... ]
}
```

---

## Platform Support Details

### extractors/

The `extractors` subpackage contains all platform-specific extractors.

#### extractors/__init__.py

Re-exports the complete public extractor API:

| Symbol | Description |
|---|---|
| `BaseExtractor` | Abstract base class |
| `ExtractorRegistry` | Registry class |
| `registry` | Global registry instance |
| `register_extractor` | Registration decorator |
| `YouTubeExtractor` | YouTube extractor |
| `TwitchExtractor` | Twitch extractor |
| `VimeoExtractor` | Vimeo extractor |
| `GenericExtractor` | Generic website extractor |
| `PlaylistExtractor` | M3U/PLS playlist extractor |

---

#### extractors/base.py

Base extractor and extractor registry. Extractors are responsible for fetching and parsing media content from specific platforms or website types.

##### `BaseExtractor(ABC)`

Abstract base class for media extractors. Each extractor handles a specific platform or type of content.

**Subclasses must implement or define:**

- `PLATFORM: Platform` — The platform this extractor handles (class attribute).
- `URL_PATTERNS: List[Pattern]` — Regex patterns to match URLs (class attribute).
- `async extract(request: ScanRequest) -> ScanResult` — The main extraction method.

**Class methods:**

- `can_handle(url) -> bool` — Returns `True` if any `URL_PATTERNS` entry matches the URL.
- `match_url(url) -> Optional[re.Match]` — Returns the first regex match object for matching patterns, or `None`.

**Instance methods:**

- `async extract(request) -> ScanResult` — Abstract. Must be implemented by subclasses.
- `async extract_stream_url(item) -> Optional[str]` — Extract the actual stream URL for a media item. Some platforms require additional requests. Default returns `item.stream_url`; override as needed.
- `_create_result(request) -> ScanResult` — Creates a new `ScanResult` with `status=SCANNING` for this extraction.
- `_parse_duration(duration_str) -> Optional[int]` — Parses a duration string to seconds. Supports: ISO 8601 (`PT1H2M3S`), `HH:MM:SS`, `MM:SS`, and plain integer seconds.
- `_detect_quality(height=None, label=None) -> StreamQuality` — Maps pixel height or quality label string to a `StreamQuality` enum. Height thresholds: ≥2160→4K, ≥1440→1440p, ≥1080→1080p, ≥720→720p, ≥480→480p, ≥360→360p, else→240p. Label matching is case-insensitive.
- `_detect_protocol(url) -> StreamProtocol` — Detects stream protocol from URL. Checks for `.m3u8`/`hls` (HLS), `.mpd`/`dash` (DASH), `rtmp://` (RTMP), `rtsp://` (RTSP), video file extensions (PROGRESSIVE), `http(s)://` (HTTP).

##### `ExtractorRegistry`

Registry of available extractors. Automatically selects the appropriate extractor for a given URL.

**Methods:**

- `register(extractor_class)` — Registers an extractor class (skips duplicates). Logs at DEBUG level.
- `get_extractor(url) -> Optional[BaseExtractor]` — Returns a cached instance of the first extractor whose `can_handle(url)` returns `True`. Creates the instance on first use.
- `get_platform(url) -> Platform` — Returns the `PLATFORM` of the matching extractor, or `Platform.UNKNOWN`.

**Property:**

- `registered_extractors` — Returns a copy of the list of registered extractor classes.

**Module-level globals:**

- `registry = ExtractorRegistry()` — Global registry instance.
- `register_extractor(cls)` — Decorator that calls `registry.register(cls)` and returns the class unchanged.

---

#### extractors/generic.py

Generic website media extractor. Scans websites for video content by detecting:
- Direct video file links (mp4, webm, etc.)
- HLS/DASH manifests (m3u8, mpd)
- Embedded video players (`<video>` tags, `<iframe>` elements)
- Common video platforms (embedded YouTube, Vimeo, etc.)

##### `GenericExtractor(BaseExtractor)`

Generic extractor for websites with video content. Decorated with `@register_extractor`.

Scans HTML pages for:
- `<video>` tags with `src` attributes
- `<source>` elements within video tags
- `<iframe>` embeds of video platforms
- Direct links to video files
- HLS/DASH manifest URLs in scripts
- JSON-LD structured data

**Class attributes:**

- `PLATFORM = Platform.WEBSITE`
- `URL_PATTERNS` — Matches any `http://` or `https://` URL (acts as the fallback extractor).
- `VIDEO_EXTENSIONS` — Set: `{'.mp4', '.m4v', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.ts', '.m3u8', '.mpd'}`.
- `MEDIA_PATTERNS` — List of compiled regexes for finding media URLs in scripts. Patterns cover `.m3u8`, `.mpd`, `.mp4`, `.webm`, and common JS player property names (`file`, `source`, `videoUrl`, `streamUrl`, `hlsUrl`, `manifestUrl`).

**Methods:**

- `async extract(request) -> ScanResult` — Entry point. Calls `_scan_page` recursively, then sets `status=COMPLETED`. Records `started_at`, `completed_at`, and `duration_ms`.
- `async _scan_page(result, url, visited, depth, max_depth, follow_links, max_items)` — Scans a single page. Skips already-visited URLs and stops when `max_items` is reached. Fetches page, extracts metadata (title on depth 0), finds media URLs, creates `MediaItem` objects, follows links if enabled and depth allows. Links are limited to same-domain same-domain URLs, excluding `.jpg`, `.png`, `.gif`, `.css`, `.js`, `.pdf` extensions. At most 20 links are followed per page.
- `_find_media_urls(html, base_url) -> List[Tuple[str, MediaType, Dict]]` — Orchestrates all extraction strategies in order: video tags, iframes, scripts, JSON-LD. Deduplicates by URL. HLS (`.m3u8`) items are classified as `LIVE`, others as `VOD`.
- `_extract_video_tags(html, base_url)` — Finds `<video>` tags (including self-closing), extracts `poster` as thumbnail, `src` attribute and `<source>` child `src` attributes.
- `_extract_iframes(html, base_url)` — Finds `<iframe src="...">` elements. Only includes iframes from known video domains: `youtube.com`, `youtube-nocookie.com`, `youtu.be`, `vimeo.com`, `player.vimeo.com`, `dailymotion.com`, `dai.ly`, `twitch.tv`, `player.twitch.tv`, `facebook.com`, `fb.watch`, `rumble.com`.
- `_extract_from_scripts(html, base_url)` — Extracts all `<script>` blocks and applies `MEDIA_PATTERNS` to find media URLs. Handles `//`-protocol-relative URLs by prepending `https:`.
- `_extract_json_ld(html, base_url)` — Parses `<script type="application/ld+json">` blocks. Extracts `contentUrl` and `embedUrl` from `VideoObject` (or any `@type` containing `"Video"`). Captures `name`, `description`, `thumbnailUrl`, and `duration` (parsed via `_parse_duration`) as metadata.
- `_extract_links(html, base_url) -> List[str]` — Extracts `<a href>` links from HTML, filtered to same-domain non-resource URLs. Returns at most 20 links.
- `_extract_title(html) -> Optional[str]` — Extracts page title from `<title>` tag or `og:title` meta property.
- `_is_video_url(url) -> bool` — Returns `True` if URL path contains a known video extension or if the URL contains streaming keywords (`stream`, `video`, `media`, `player`, `hls`, `dash`).
- `_generate_title(url) -> str` — Derives a human-readable title from the URL path (strips extension, replaces `_` and `-` with spaces). Falls back to `netloc` if the path yields no filename.

---

#### extractors/playlist.py

Playlist file extractor. Extracts media items from M3U, M3U8, and PLS playlist files.

##### `PlaylistExtractor(BaseExtractor)`

Extractor for playlist files (M3U, M3U8, PLS). Parses playlist files to extract media items. Useful for importing existing IPTV lists or bulk-importing streams. Decorated with `@register_extractor`.

**Class attributes:**

- `PLATFORM = Platform.PLAYLIST`
- `URL_PATTERNS` — Matches `.m3u`, `.m3u8`, and `.pls` URLs (with optional query string).

**Methods:**

- `async extract(request) -> ScanResult` — Fetches the playlist URL. Auto-detects format: uses M3U parser if `#EXTM3U` is in content or URL ends with `.m3u`/`.m3u8`; uses PLS parser if `[playlist]` is in content (case-insensitive); falls back to M3U parser otherwise.
- `_parse_m3u(content, request) -> List[MediaItem]` — Parses M3U content line by line. `#EXTINF:` lines are parsed into `MediaItem` stubs by `_parse_extinf`. Subsequent URL lines are attached. Duration of `-1` → `LIVE`; positive duration → `VOD`. Stops at `max_items`.
- `_parse_extinf(line) -> MediaItem` — Parses an `#EXTINF:` directive. Format: `#EXTINF:duration [attributes],Title`. Duration of `-1` marks item as live. Standard attributes parsed: `tvg-id`, `tvg-logo`, `group-title`, `tvg-name`.
- `_parse_pls(content, request) -> List[MediaItem]` — Parses PLS (INI-style) content using `configparser`. Reads `NumberOfEntries`, then `File{i}`, `Title{i}`, `Length{i}` for each entry. Length of `-1` → `LIVE`; positive → `VOD`. Logs a warning on parse error.

---

#### extractors/twitch.py

Twitch media extractor. Extracts live streams, VODs, and clips from Twitch.

##### `TwitchExtractor(BaseExtractor)`

Extractor for Twitch content. Decorated with `@register_extractor`.

**Supported content types:**

- Live streams
- VODs (past broadcasts)
- Clips
- Channels (fetches live stream + VODs)

**Class attributes:**

- `PLATFORM = Platform.TWITCH`
- `URL_PATTERNS` — Matches: channel URLs (`twitch.tv/{channel}`), channel videos (`twitch.tv/{channel}/videos`), VOD URLs (`twitch.tv/videos/{vod_id}`), clip URLs (`twitch.tv/{channel}/clip/{clip_id}`, `clips.twitch.tv/{clip_id}`).
- `GQL_URL = "https://gql.twitch.tv/gql"` — Twitch GraphQL endpoint.
- `CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"` — Public Twitch client ID used for GQL requests.

**Methods:**

- `async extract(request) -> ScanResult` — Dispatches to `_extract_vod`, `_extract_clip`, or `_extract_channel` based on URL pattern. Records `started_at`, `completed_at`, and `duration_ms`.
- `async _gql_request(operations) -> Optional[List[Dict]]` — POSTs a GraphQL operation list to `GQL_URL` with `Client-ID` header. Returns parsed JSON or `None` on failure.
- `async _extract_channel(result, channel, request)` — Fetches channel shell data via `ChannelShell` GQL operation. Extracts display name, profile image. If stream data is present, calls `_parse_live_stream`. If `request.include_vod` is `True`, calls `_get_channel_vods`.
- `async _parse_live_stream(channel, channel_data, stream_data) -> Optional[MediaItem]` — Builds a `MediaItem` for a live stream. Sets `is_live=True`, `media_type=LIVE`. Replaces `{width}`/`{height}` in preview URL with `1280`/`720`. Fetches the actual HLS stream URL via `_get_stream_url`.
- `async _get_stream_url(channel) -> Optional[str]` — Obtains a playback access token via `PlaybackAccessToken` GQL operation and constructs an HLS URL: `https://usher.ttvnw.net/api/channel/hls/{channel}.m3u8?token=...&sig=...&allow_source=true&allow_audio_only=true`.
- `async _extract_vod(vod_id) -> Optional[MediaItem]` — Fetches VOD metadata via `VideoMetadata` GQL operation. Extracts title, description, duration, thumbnail (replaces `%{width}`/`%{height}` with `1280`/`720`), channel info, view count, upload date (ISO-format parsed), game/category.
- `async _extract_clip(clip_id) -> Optional[MediaItem]` — Fetches clip metadata via `ClipMetadata` GQL operation. Extracts title, duration, thumbnail, broadcaster info, view count, and first `videoQualities.sourceURL` as `stream_url` with `PROGRESSIVE` protocol.
- `async _get_channel_vods(channel, limit=20) -> List[MediaItem]` — Fetches up to `min(limit, 30)` VODs via `FilterableVideoTower_Videos` GQL operation sorted by time (archive broadcasts only).

---

#### extractors/vimeo.py

Vimeo media extractor. Extracts videos from Vimeo channels, users, and direct video links.

##### `VimeoExtractor(BaseExtractor)`

Extractor for Vimeo content. Decorated with `@register_extractor`.

**Supported content types:**

- Individual videos
- User profiles
- Channels
- Showcases

**Class attributes:**

- `PLATFORM = Platform.VIMEO`
- `URL_PATTERNS` — Matches: video URLs (`vimeo.com/{id}`, `player.vimeo.com/video/{id}`), user URLs (`vimeo.com/{user}`, `vimeo.com/{user}/videos`), channel URLs (`vimeo.com/channels/{channel}`), showcase URLs (`vimeo.com/showcase/{showcase}`).
- `API_URL = "https://api.vimeo.com"`
- `PLAYER_URL = "https://player.vimeo.com/video"`

**Methods:**

- `async extract(request) -> ScanResult` — Dispatches to `_extract_video`, `_extract_channel`, or `_extract_user` based on URL pattern. Skips `channels`, `showcase`, `watch`, and `features` path segments for user URLs. Records timing.
- `async _extract_video(video_id) -> Optional[MediaItem]` — Fetches the Vimeo player page for the video and calls `_extract_player_config`, then `_parse_video_config`.
- `_extract_player_config(html) -> Optional[Dict]` — Looks for player config JSON in the page using three patterns: `window.playerConfig = {...}`, `"config": {...}`, `config = {...}`. Falls back to scanning script blocks for `cdn_url` or `progressive`.
- `_parse_video_config(video_id, config) -> Optional[MediaItem]` — Parses title, duration, thumbnail (from `thumbs` dict, tries sizes `1280`, `960`, `640`, `480`, `base`), owner/channel info, and extracts streams. Stream extraction order: HLS (first CDN entry), DASH (first CDN entry), progressive (sorted by height descending, quality detected by `_detect_quality`).
- `async _extract_user(result, username, request)` — Fetches `vimeo.com/{username}/videos`, extracts video IDs via `data-clip-id` and `iris_video` class patterns, deduplicates, then calls `_extract_video` for each up to `max_items`. Sets `status=PARTIAL` on error.
- `async _extract_channel(result, channel, request)` — Fetches `vimeo.com/channels/{channel}/videos`, extracts numeric video IDs (must be > 5 digits) via `data-clip-id` and generic `"/(\d+)"` patterns, deduplicates, then calls `_extract_video` for each up to `max_items`. Sets `status=PARTIAL` on error.

---

#### extractors/youtube.py

YouTube media extractor. Extracts videos, playlists, channels, and live streams from YouTube.

##### `YouTubeExtractor(BaseExtractor)`

Extractor for YouTube content. Decorated with `@register_extractor`.

**Supported content types:**

- Individual videos
- Playlists
- Channels (videos, live streams)
- Shorts
- Live streams

**Class attributes:**

- `PLATFORM = Platform.YOUTUBE`
- `URL_PATTERNS` — Matches: standard video URLs (`youtube.com/watch?v=`, `youtube.com/v/`, `youtube.com/embed/`, `youtu.be/`), Shorts (`youtube.com/shorts/`), live streams (`youtube.com/live/`), playlists (`youtube.com/playlist?list=`), channels (`youtube.com/channel/`, `youtube.com/c/`, `youtube.com/@`, `youtube.com/user/`).
- `INNERTUBE_API = "https://www.youtube.com/youtubei/v1"` — YouTube internal API endpoint.
- `INNERTUBE_CLIENT = {"clientName": "WEB", "clientVersion": "2.20231219.04.00"}` — YouTube client context.

**Methods:**

- `async extract(request) -> ScanResult` — Dispatches to `_extract_playlist`, `_extract_channel`, or `_extract_video` based on URL patterns (playlist query param, channel/c/@/user path, or single video ID). Records timing.
- `_extract_video_id(url) -> Optional[str]` — Extracts video ID from URL query param `v`, or from path patterns (`/v/`, `/embed/`, `/shorts/`, `/live/`, `youtu.be/`).
- `async _extract_video(video_id) -> Optional[MediaItem]` — Fetches `youtube.com/watch?v={id}`, extracts `ytInitialPlayerResponse`, and parses via `_parse_video_data`.
- `_extract_player_response(html) -> Optional[Dict]` — Searches for `var ytInitialPlayerResponse = {...}` in page HTML using two patterns.
- `_parse_video_data(video_id, player_response) -> Optional[MediaItem]` — Parses `videoDetails` and `streamingData`. Sets `is_live`/`is_upcoming` flags. Extracts thumbnail (highest width from `thumbnail.thumbnails`), channel info, view count, age restriction, tags, and streams via `_extract_streams`. For live streams, uses `hlsManifestUrl` if present.
- `_extract_streams(streaming_data) -> List[StreamInfo]` — Parses `adaptiveFormats` and `formats` from streaming data, calling `_parse_format` on each.
- `_parse_format(fmt) -> Optional[StreamInfo]` — Parses a single format entry. Skips entries without a `url` (signatureCipher entries are not decoded). Extracts quality, protocol, dimensions, bitrate, fps, and codecs.
- `async _extract_playlist(result, playlist_id, request)` — Fetches `youtube.com/playlist?list={id}`, extracts `ytInitialData`, finds playlist contents via `_find_playlist_data`, and parses each video via `_parse_playlist_video`. Sets `source_title` from playlist metadata.
- `_extract_initial_data(html) -> Optional[Dict]` — Searches for `var ytInitialData = {...}` in page HTML.
- `_find_playlist_data(initial_data) -> Optional[Dict]` — Navigates `twoColumnBrowseResultsRenderer → tabs → tabRenderer → content → sectionListRenderer → contents → itemSectionRenderer → contents → playlistVideoListRenderer` to extract `title` and `contents`.
- `_parse_playlist_video(video_data) -> Optional[MediaItem]` — Parses `playlistVideoRenderer`. Extracts `videoId`, title (from `title.runs[0].text`), duration from `lengthSeconds`, thumbnail, and channel name/ID from `shortBylineText.runs[0]`.
- `async _extract_channel(result, url, request)` — Appends `/videos` to the URL if not present, fetches it, extracts `ytInitialData`, parses channel metadata (`channelMetadataRenderer`), and collects videos via `_find_channel_videos` + `_parse_channel_video`.
- `_find_channel_videos(initial_data) -> List[Dict]` — Navigates both the rich grid layout (`richGridRenderer → richItemRenderer → videoRenderer`) and the section list layout (`sectionListRenderer → itemSectionRenderer → gridRenderer → gridVideoRenderer`) to collect video data dictionaries.
- `_parse_channel_video(video_data) -> Optional[MediaItem]` — Parses a channel video entry. Checks badge styles for `LIVE` to set `is_live`. Parses duration from `lengthText.simpleText` via `_parse_duration`. Extracts thumbnail and view count (parses `"1,234 views"` strings with regex).

---

## Configuration Reference

### Environment Variables

| Variable | Config Field | Default | Description |
|---|---|---|---|
| `YOUTUBE_API_KEY` | `YouTubeConfig.api_key` | `None` | YouTube Data API key (optional; enables higher rate limits) |
| `TWITCH_CLIENT_ID` | `TwitchConfig.client_id` | `None` | Twitch API client ID |
| `TWITCH_CLIENT_SECRET` | `TwitchConfig.client_secret` | `None` | Twitch API client secret |
| `HTTP_PROXY` | `NetworkConfig.proxies` | `None` | HTTP proxy URL (added to proxy pool) |
| `HTTPS_PROXY` | `NetworkConfig.proxies` | `None` | HTTPS proxy URL (added to proxy pool, deduplicated) |
| `PROXY_LIST` | `NetworkConfig.proxies` | `None` | Comma-separated list of proxy URLs |
| `PROXY_FILE` | `NetworkConfig.proxy_file` | `None` | Path to a file containing one proxy URL per line (lines starting with `#` are ignored) |

---

## Project Structure

```
scanner/
├── __init__.py          # Package init, public API re-exports
├── config.py            # Configuration dataclasses (NetworkConfig, YouTubeConfig, etc.)
├── http_client.py       # Async HTTP client with retries, rate limiting, proxy support
├── models.py            # Data models (MediaItem, ScanResult, enums)
├── scanner.py           # MediaScanner class, scan_url() convenience function
├── routes.py            # Flask Blueprint with REST API endpoints
├── extractors/
│   ├── __init__.py      # Extractor package init
│   ├── base.py          # BaseExtractor ABC, ExtractorRegistry, register_extractor decorator
│   ├── generic.py       # GenericExtractor — scrapes any HTTP(S) website
│   ├── playlist.py      # PlaylistExtractor — parses M3U, M3U8, PLS files
│   ├── twitch.py        # TwitchExtractor — GQL-based Twitch extractor
│   ├── vimeo.py         # VimeoExtractor — Vimeo player page scraper
│   └── youtube.py       # YouTubeExtractor — YouTube ytInitialData scraper
├── requirements.txt
└── README.md
```

### Adding New Extractors

1. Create a new file in `extractors/`.
2. Subclass `BaseExtractor`.
3. Define `PLATFORM` (a `Platform` enum value) and `URL_PATTERNS` (list of compiled regexes).
4. Implement the `async extract(request)` method.
5. Apply the `@register_extractor` decorator.
6. Import the new extractor in `extractors/__init__.py`.

```python
import re
from scanner.extractors.base import BaseExtractor, register_extractor
from scanner.models import Platform, ScanRequest, ScanResult

@register_extractor
class MyExtractor(BaseExtractor):
    PLATFORM = Platform.UNKNOWN
    URL_PATTERNS = [
        re.compile(r'mysite\.com/video/(\d+)'),
    ]

    async def extract(self, request: ScanRequest) -> ScanResult:
        result = self._create_result(request)
        # ... extraction logic ...
        return result
```
