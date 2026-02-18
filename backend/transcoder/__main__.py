#!/usr/bin/env python3
"""
IPTV Transcoding Backend Server - Entry Point

Starts the transcoding server with FFmpeg validation and startup diagnostics.

Usage::

    python -m transcoder
    python transcoder/__main__.py

See ``transcoder/config.py`` for the full list of environment variables.
"""

import subprocess
import sys
from typing import Tuple

from transcoder import __version__
from transcoder.app import create_app
from transcoder.config import config


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def check_ffmpeg() -> Tuple[bool, str]:
    """
    Verify FFmpeg is present and return its version string.

    Returns:
        ``(True, version_line)`` on success, ``(False, reason)`` on failure.
    """
    try:
        result = subprocess.run(
            [config.ffmpeg.path, '-version'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.split('\n')[0]
        return False, f"FFmpeg exited with code {result.returncode}"
    except FileNotFoundError:
        return False, f"FFmpeg not found at '{config.ffmpeg.path}'"
    except subprocess.TimeoutExpired:
        return False, "FFmpeg version check timed out"
    except Exception as exc:
        return False, str(exc)


def check_ffprobe() -> Tuple[bool, str]:
    """
    Verify ffprobe is present and return its version string.

    Returns:
        ``(True, version_line)`` on success, ``(False, reason)`` on failure.
    """
    try:
        result = subprocess.run(
            [config.ffmpeg.probe_path, '-version'],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, result.stdout.split('\n')[0]
        return False, f"ffprobe exited with code {result.returncode}"
    except FileNotFoundError:
        return False, f"ffprobe not found at '{config.ffmpeg.probe_path}'"
    except subprocess.TimeoutExpired:
        return False, "ffprobe version check timed out"
    except Exception as exc:
        return False, str(exc)


def check_waitress() -> bool:
    """Return True if the Waitress WSGI server is importable."""
    try:
        import waitress  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Console output helpers  — ASCII-safe, no emoji
# ---------------------------------------------------------------------------

_OK   = "[OK]"
_WARN = "[WARN]"
_FAIL = "[FAIL]"


def _line(char: str = "-", width: int = 70) -> str:
    return char * width


def print_banner() -> None:
    print(_line("="))
    print(f"  IPTV TRANSCODING BACKEND SERVER  v{__version__}")
    print(_line("="))
    print()


def print_ffmpeg_status(ffmpeg_ok: bool, ffmpeg_ver: str,
                        ffprobe_ok: bool, ffprobe_ver: str) -> None:
    tag = _OK if ffmpeg_ok else _FAIL
    print(f"{tag} FFmpeg  : {ffmpeg_ver}")
    tag = _OK if ffprobe_ok else _FAIL
    print(f"{tag} ffprobe : {ffprobe_ver}")

    if not ffmpeg_ok or not ffprobe_ok:
        print()
        print("  FFmpeg and ffprobe are both required.")
        print("  Install from : https://ffmpeg.org/download.html")
        print("  Windows      : Download and add to PATH")
        print("  macOS        : brew install ffmpeg")
        print("  Linux        : sudo apt install ffmpeg")


def print_server_status(use_waitress: bool) -> None:
    if use_waitress:
        print(f"{_OK} Server  : Waitress (production WSGI)")
    else:
        print(f"{_WARN} Server  : Flask development server")
        print(f"         Install waitress for production: pip install waitress")


def print_config() -> None:
    print()
    print("Configuration")
    print(_line())
    print(f"  Host              : {config.server.host}")
    print(f"  Port              : {config.server.port}")
    print(f"  Debug             : {config.server.debug}")
    print(f"  Log level         : {config.log.level}")
    print(f"  Video codec       : {config.video.codec} (smart transcode)")
    print(f"  Audio codec       : {config.audio.codec} @ {config.audio.bitrate}")
    print(f"  FFmpeg preset     : {config.ffmpeg.preset}  CRF={config.ffmpeg.crf}")
    print(f"  Probe timeout     : {config.ffmpeg.probe_timeout}s")
    print(f"  Read timeout      : {config.ffmpeg.read_timeout}s")
    print(f"  Max streams       : {config.stream.max_concurrent}")
    print(f"  Max per IP        : {config.stream.max_per_ip}")
    print(f"  Idle timeout      : {config.stream.idle_timeout}s")
    print(f"  Max retries       : {config.ffmpeg.max_retries}")
    print(f"  HLS segment dir   : {config.hls.segment_dir}")
    print(f"  HLS seg duration  : {config.hls.segment_duration}s")
    print(f"  Auth enabled      : {config.auth.enabled}")


def print_endpoints() -> None:
    base = f"http://{config.server.host}:{config.server.port}"
    lock = " [auth]" if config.auth.enabled else ""

    print()
    print("API Endpoints")
    print(_line())
    rows = [
        ("GET",    "/api/health",                        "Health check"),
        ("GET",    "/api/stats",                         "Server statistics"),
        ("GET",    "/api/stream?url=<URL>",              "Create / get stream"),
        ("POST",   "/api/stream",                        f"Create stream (JSON){lock}"),
        ("GET",    "/api/stream/<id>",                   "Stream info"),
        ("GET",    "/api/stream/<id>/status",            "Detailed status"),
        ("DELETE", "/api/stream/<id>",                   f"Stop stream{lock}"),
        ("GET",    "/api/streams",                       "List all streams"),
        ("POST",   "/api/streams/stop-all",              f"Stop all streams{lock}"),
        ("GET",    "/api/stream/<id>/playlist.m3u8",     "HLS playlist"),
        ("GET",    "/api/stream/<id>/segments/<file>",   "HLS segment"),
        ("GET",    "/api/probe?url=<URL>",               "Probe codecs"),
    ]
    for method, path, desc in rows:
        print(f"  {method:<7} {base}{path}")
        print(f"          {desc}")

    if config.auth.enabled:
        print()
        print("  [auth] endpoints require the X-API-Key header.")


def print_examples() -> None:
    port = config.server.port
    auth = f"-H 'X-API-Key: <key>' " if config.auth.enabled else ""

    print()
    print("Examples")
    print(_line())
    print(f"  curl http://localhost:{port}/api/health")
    print()
    print(f"  # Start a stream")
    print(f"  curl 'http://localhost:{port}/api/stream?url=http://example.com/live.ts'")
    print()
    print(f"  # Start a stream (POST)")
    print(f"  curl -X POST http://localhost:{port}/api/stream \\")
    print(f"       -H 'Content-Type: application/json' \\")
    if config.auth.enabled:
        print(f"       -H 'X-API-Key: <your-key>' \\")
    print(f"       -d '{{\"url\": \"http://example.com/stream.m3u8\"}}'")
    print()
    print(f"  # Point an HLS player at:")
    print(f"  http://localhost:{port}/api/stream/<id>/playlist.m3u8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Start the transcoding server."""
    print_banner()

    # --- FFmpeg / ffprobe checks ---
    ffmpeg_ok, ffmpeg_ver = check_ffmpeg()
    ffprobe_ok, ffprobe_ver = check_ffprobe()
    print_ffmpeg_status(ffmpeg_ok, ffmpeg_ver, ffprobe_ok, ffprobe_ver)

    if not ffmpeg_ok or not ffprobe_ok:
        print()
        print("Startup aborted: FFmpeg and ffprobe must both be available.")
        sys.exit(1)

    # --- WSGI server check ---
    use_waitress = check_waitress()
    print_server_status(use_waitress)

    print_config()
    print_endpoints()
    print_examples()

    print()
    print(_line("="))
    print(f"  Starting on http://{config.server.host}:{config.server.port}  "
          f"(Press Ctrl+C to stop)")
    print(_line("="))
    print()

    app = create_app()

    try:
        if use_waitress:
            import waitress
            waitress.serve(
                app,
                host=config.server.host,
                port=config.server.port,
                threads=config.stream.max_concurrent + 4,
            )
        else:
            app.run(
                host=config.server.host,
                port=config.server.port,
                debug=config.server.debug,
                threaded=True,
                use_reloader=False,   # prevent duplicate cleanup threads
            )
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        from transcoder.manager import manager
        manager.stop_all()
        print("Server stopped.")


if __name__ == '__main__':
    main()