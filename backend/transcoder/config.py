"""
Configuration settings for the transcoding server.

Each sub-config class declares its fields with explicit defaults.  All
environment variable reads are centralised in the ``_ENV`` mapping at the
bottom of this module — there is exactly one place to look up which env var
controls which field.

Environment variable reference
-------------------------------
FFMPEG_PATH            Path to the ffmpeg binary          (default: ffmpeg)
FFPROBE_PATH           Path to the ffprobe binary         (default: ffprobe)
FFMPEG_PRESET          Encoding preset                    (default: ultrafast)
FFMPEG_CRF             Constant rate factor               (default: 28)
FFMPEG_THREADS         Encoder thread count               (default: 2)
FFMPEG_PROBE_TIMEOUT   Seconds before ffprobe gives up    (default: 10)
FFMPEG_READ_TIMEOUT    Seconds before ffmpeg read stalls  (default: 30)
FFMPEG_MAX_RETRIES     Auto-restart attempts              (default: 3)
FFMPEG_RETRY_DELAY     Seconds between retries            (default: 2.0)
AUDIO_BITRATE          AAC bitrate                        (default: 192k)
AUDIO_CHANNELS         Audio channel count                (default: 2)
AUDIO_SAMPLE_RATE      Audio sample rate in Hz            (default: 48000)
VIDEO_COPYABLE_CODECS  Comma-separated copy-safe codecs   (default: h264,avc,h265,hevc)
HLS_SEGMENT_DURATION   Seconds per HLS segment            (default: 6)
HLS_PLAYLIST_SIZE      Segments kept in playlist          (default: 5)
HLS_SEGMENT_DIR        Directory for HLS segment files    (default: <tempdir>/iptv-transcoder-hls)
STREAM_BUFFER_SIZE         Read buffer size in bytes            (default: 8192)
MAX_CONCURRENT_STREAMS     Maximum simultaneous streams         (default: 10)
MAX_STREAMS_PER_IP         Maximum streams per client IP        (default: 3)
STREAM_IDLE_TIMEOUT        Seconds before idle stream stops     (default: 300)
STREAM_CLEANUP_INTERVAL    Seconds between cleanup sweeps       (default: 60)
STREAM_HEALTH_POLL         Seconds between health-monitor polls (default: 3)
STREAM_HEALTH_STARTUP      Seconds before first health poll     (default: 2)
FFMPEG_RECONNECT_DELAY_MAX Max reconnect back-off seconds       (default: 5)
FFMPEG_LOGLEVEL            FFmpeg stderr log level              (default: warning)
FFMPEG_STDERR_BUFFER       Lines of stderr to keep in memory    (default: 1000)
HLS_CLEANUP_DELAY          Seconds to keep segments after stop  (default: 30)
HOST                       Server bind address                  (default: 0.0.0.0)
PORT                   Server bind port                   (default: 5000)
DEBUG                  Enable Flask debug mode            (default: false)
LOG_LEVEL              Logging level name                 (default: INFO)
API_KEY                Shared secret for protected routes (default: <unset>)
"""

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {key}={raw!r} is not a valid integer") from exc


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {key}={raw!r} is not a valid float") from exc


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ('1', 'true', 'yes')


def _env_codec_tuple(key: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    """Parse a comma-separated list of codec names from an env var."""
    raw = os.getenv(key)
    if raw is None:
        return default
    return tuple(c.strip().lower() for c in raw.split(',') if c.strip())


# ---------------------------------------------------------------------------
# Sub-configs
# ---------------------------------------------------------------------------

@dataclass
class FFmpegConfig:
    """FFmpeg binary paths, encoding settings, timeouts, and retry policy."""

    path: str = field(default_factory=lambda: _env_str('FFMPEG_PATH', 'ffmpeg'))
    probe_path: str = field(default_factory=lambda: _env_str('FFPROBE_PATH', 'ffprobe'))

    # Encoding settings
    preset: str = field(default_factory=lambda: _env_str('FFMPEG_PRESET', 'ultrafast'))
    crf: int = field(default_factory=lambda: _env_int('FFMPEG_CRF', 28))
    threads: int = field(default_factory=lambda: _env_int('FFMPEG_THREADS', 2))

    # Timeouts — two distinct values with unambiguous names:
    #   probe_timeout : how long ffprobe may run before being killed
    #   read_timeout  : how long ffmpeg waits for data before treating the
    #                   stream as stalled (passed via -timeout / -rw_timeout)
    probe_timeout: int = field(default_factory=lambda: _env_int('FFMPEG_PROBE_TIMEOUT', 10))
    read_timeout: int = field(default_factory=lambda: _env_int('FFMPEG_READ_TIMEOUT', 30))

    reconnect_delay_max: int = field(
        default_factory=lambda: _env_int('FFMPEG_RECONNECT_DELAY_MAX', 5)
    )

    # Logging
    loglevel: str = field(default_factory=lambda: _env_str('FFMPEG_LOGLEVEL', 'warning'))
    stderr_buffer_lines: int = field(
        default_factory=lambda: _env_int('FFMPEG_STDERR_BUFFER', 1000)
    )

    # Retry settings
    max_retries: int = field(default_factory=lambda: _env_int('FFMPEG_MAX_RETRIES', 3))
    retry_delay: float = field(default_factory=lambda: _env_float('FFMPEG_RETRY_DELAY', 2.0))


@dataclass
class AudioConfig:
    """Audio encoding configuration."""

    codec: str = 'aac'
    bitrate: str = field(default_factory=lambda: _env_str('AUDIO_BITRATE', '192k'))
    channels: int = field(default_factory=lambda: _env_int('AUDIO_CHANNELS', 2))
    sample_rate: str = field(default_factory=lambda: _env_str('AUDIO_SAMPLE_RATE', '48000'))


@dataclass
class VideoConfig:
    """Video encoding configuration."""

    codec: str = 'copy'           # smart transcoding: copy by default
    fallback_codec: str = 'libx264'
    bitrate: str = '2500k'
    scale: str = '1280:720'

    # Env-var overridable tuple of codec names safe to copy without re-encoding.
    # Consumed by CodecInfo.can_copy_video(config.video.copyable_codecs).
    copyable_codecs: Tuple[str, ...] = field(
        default_factory=lambda: _env_codec_tuple(
            'VIDEO_COPYABLE_CODECS',
            ('h264', 'avc', 'h265', 'hevc'),
        )
    )


@dataclass
class HLSConfig:
    """HLS output configuration."""

    segment_duration: int = field(default_factory=lambda: _env_int('HLS_SEGMENT_DURATION', 6))
    playlist_size: int = field(default_factory=lambda: _env_int('HLS_PLAYLIST_SIZE', 5))
    segment_dir: str = field(
        default_factory=lambda: _env_str(
            'HLS_SEGMENT_DIR',
            os.path.join(tempfile.gettempdir(), 'iptv-transcoder-hls'),
        )
    )
    segment_format: str = 'mpegts'
    cleanup_delay: int = field(
        default_factory=lambda: _env_int('HLS_CLEANUP_DELAY', 30)
    )


@dataclass
class StreamConfig:
    """Stream management configuration."""

    buffer_size: int = field(default_factory=lambda: _env_int('STREAM_BUFFER_SIZE', 8192))
    cleanup_interval: int = field(
        default_factory=lambda: _env_int('STREAM_CLEANUP_INTERVAL', 60)
    )
    health_poll_interval: int = field(
        default_factory=lambda: _env_int('STREAM_HEALTH_POLL', 3)
    )
    health_startup_delay: int = field(
        default_factory=lambda: _env_int('STREAM_HEALTH_STARTUP', 2)
    )
    idle_timeout: int = field(default_factory=lambda: _env_int('STREAM_IDLE_TIMEOUT', 300))
    max_concurrent: int = field(default_factory=lambda: _env_int('MAX_CONCURRENT_STREAMS', 10))
    max_per_ip: int = field(default_factory=lambda: _env_int('MAX_STREAMS_PER_IP', 3))
    output_format: str = 'mpegts'


@dataclass
class ServerConfig:
    """Flask server configuration."""

    host: str = field(default_factory=lambda: _env_str('HOST', '0.0.0.0'))
    port: int = field(default_factory=lambda: _env_int('PORT', 5000))
    debug: bool = field(default_factory=lambda: _env_bool('DEBUG', False))

    # CORS settings
    cors_origins: str = '*'
    cors_methods: List[str] = field(default_factory=lambda: ['GET', 'POST', 'DELETE', 'OPTIONS'])
    cors_headers: List[str] = field(default_factory=lambda: ['Content-Type', 'X-API-Key'])


@dataclass
class AuthConfig:
    """API authentication configuration."""

    api_key: Optional[str] = field(default_factory=lambda: os.getenv('API_KEY'))

    @property
    def enabled(self) -> bool:
        """Auth is enabled when an API key is configured."""
        return bool(self.api_key)


@dataclass
class LogConfig:
    """Logging configuration."""

    level: int = field(
        default_factory=lambda: getattr(
            logging,
            _env_str('LOG_LEVEL', 'INFO').upper(),
            logging.INFO,
        )
    )
    format: str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """
    Root configuration container.  Instantiate once; import the singleton
    ``config`` everywhere else.

    All env var reads happen inside ``default_factory`` callables on the
    sub-config fields, so the values are resolved at construction time and
    there is no separate ``_apply_env_overrides`` pass.

    Usage::

        from transcoder.config import config

        print(config.ffmpeg.preset)
        print(config.server.port)
        print(config.video.copyable_codecs)
    """

    ffmpeg: FFmpegConfig = field(default_factory=FFmpegConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    hls: HLSConfig = field(default_factory=HLSConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    log: LogConfig = field(default_factory=LogConfig)


# Global singleton — import this, not Config directly.
config = Config()