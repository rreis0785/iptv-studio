"""
Flask API routes for the transcoding server.

This module defines all HTTP endpoints for stream management,
HLS serving, health checks, authentication, and status monitoring.
"""

import hmac
import logging
import os
import subprocess
import time
from functools import wraps
from typing import Callable, Optional, Tuple

from flask import Blueprint, Response, jsonify, request, send_file

from transcoder import __version__
from transcoder.config import config
from transcoder.exceptions import (
    MaxStreamsError,
    MaxStreamsPerIPError,
    StreamAlreadyExistsError,
)
from transcoder.manager import manager
from transcoder.utils import validate_url

logger = logging.getLogger(__name__)

api = Blueprint('api', __name__, url_prefix='/api')


# ---------------------------------------------------------------------------
# Module-level FFmpeg availability cache
# Checked once at import time and refreshed on /health.  Avoids spawning a
# subprocess on every stream creation request.
# ---------------------------------------------------------------------------

_ffmpeg_version: Optional[str] = None
_ffmpeg_available: bool = False


def _probe_ffmpeg() -> Tuple[bool, str]:
    """
    Check whether FFmpeg is present and return its version string.

    Returns:
        ``(available, version_string)``
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


def _refresh_ffmpeg_status() -> None:
    """Update the module-level FFmpeg availability cache."""
    global _ffmpeg_available, _ffmpeg_version
    _ffmpeg_available, _ffmpeg_version = _probe_ffmpeg()


# Populate cache at import time so the first request does not pay the cost.
_refresh_ffmpeg_status()


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

# Trusted proxy header precedence list.  Only used when the request arrives
# from a known internal address; see get_client_ip().
_PROXY_HEADERS = ('X-Forwarded-For', 'X-Real-IP')

# Networks considered internal / trusted proxies.
# Extend this list if deploying behind a load-balancer with a non-RFC-1918 IP.
_TRUSTED_PROXY_NETS = ('127.', '10.', '172.16.', '192.168.')


def get_client_ip() -> str:
    """
    Return the real client IP address.

    Proxy headers (``X-Forwarded-For``, ``X-Real-IP``) are only trusted when
    the direct TCP peer is on a private/loopback network, preventing trivial
    IP spoofing from external clients.
    """
    remote = request.remote_addr or ''

    if any(remote.startswith(net) for net in _TRUSTED_PROXY_NETS):
        for header in _PROXY_HEADERS:
            value = request.headers.get(header)
            if value:
                return value.split(',')[0].strip()

    return remote or 'unknown'


def _build_stream_response(transcoder) -> dict:
    """
    Build the standard stream creation/info response body.

    Centralises the repeated identical response dict from stream_video
    and create_stream.
    """
    return {
        'success': True,
        'stream_id': transcoder.stream_id,
        'source_url': transcoder.source_url,
        'smart_transcoding': transcoder.info.is_smart_transcoding,
        'codecs': transcoder.info.codec_info.to_dict(),
        'hls_url': f"/api/stream/{transcoder.stream_id}/playlist.m3u8",
        'status_url': f"/api/stream/{transcoder.stream_id}/status",
    }


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def handle_errors(f: Callable) -> Callable:
    """Translate known exceptions to JSON error responses."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except (MaxStreamsError, MaxStreamsPerIPError) as exc:
            return jsonify(exc.to_dict()), 429
        except StreamAlreadyExistsError as exc:
            return jsonify(exc.to_dict()), 409
        except ValueError as exc:
            return jsonify({'error': 'Bad request', 'message': str(exc)}), 400
        except RuntimeError as exc:
            logger.error("Stream start failure in %s: %s", f.__name__, exc)
            return jsonify({'error': 'Stream start failed', 'message': str(exc)}), 500
        except Exception as exc:
            logger.exception("Unhandled error in %s: %s", f.__name__, exc)
            return jsonify({'error': 'Internal server error'}), 500
    return wrapper


def require_auth(f: Callable) -> Callable:
    """
    Require a valid ``X-API-Key`` header when auth is enabled.

    Comparison uses ``hmac.compare_digest`` to avoid timing-based key
    enumeration attacks.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not config.auth.enabled:
            return f(*args, **kwargs)

        provided = request.headers.get('X-API-Key', '')
        if not provided or not hmac.compare_digest(
            provided.encode(), config.auth.api_key.encode()
        ):
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Valid X-API-Key header required',
            }), 401

        return f(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------

@api.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint.

    Also refreshes the cached FFmpeg availability status so operators
    can detect a broken FFmpeg installation without restarting.

    Returns JSON with server status, FFmpeg info, and stream count.
    """
    _refresh_ffmpeg_status()

    return jsonify({
        'status': 'ok' if _ffmpeg_available else 'degraded',
        'timestamp': time.time(),
        'ffmpeg_available': _ffmpeg_available,
        'ffmpeg_version': _ffmpeg_version,
        'active_streams': manager.active_count,
        'auth_enabled': config.auth.enabled,
        'version': __version__,
    })


@api.route('/stats', methods=['GET'])
def get_stats():
    """Return aggregate server statistics."""
    return jsonify(manager.get_stats())


# ---------------------------------------------------------------------------
# Stream Management
# ---------------------------------------------------------------------------

@api.route('/stream', methods=['GET'])
@handle_errors
def stream_video():
    """
    Create or retrieve a stream and return HLS playback info.

    Query Parameters:
        url (str): Source stream URL (required).
        id  (str): Optional custom stream ID.

    Returns JSON with stream ID and HLS playlist URL.

    Example::

        GET /api/stream?url=http://example.com/channel.ts
        GET /api/stream?url=http://example.com/live.m3u8&id=channel1
    """
    source_url = request.args.get('url', '').strip()
    custom_id  = request.args.get('id', '').strip() or None

    if not source_url:
        return jsonify({
            'error': 'Missing required parameter: url',
            'example': '/api/stream?url=http://example.com/stream.ts',
        }), 400

    valid, reason = validate_url(source_url)
    if not valid:
        return jsonify({'error': 'Invalid URL', 'message': reason}), 400

    if not _ffmpeg_available:
        return jsonify({
            'error': 'FFmpeg not available',
            'message': _ffmpeg_version,
        }), 503

    client_ip = get_client_ip()
    transcoder = manager.get_or_create_stream(source_url, custom_id, client_ip)

    logger.info(
        "Streaming %s to %s (smart_transcode=%s)",
        transcoder.stream_id,
        client_ip,
        transcoder.info.is_smart_transcoding,
    )

    return jsonify(_build_stream_response(transcoder))


@api.route('/stream', methods=['POST'])
@handle_errors
@require_auth
def create_stream():
    """
    Create a new transcoding stream.

    Request Body (JSON)::

        {"url": "http://example.com/stream.ts", "id": "optional-custom-id"}

    Returns 201 with stream details and HLS URL.
    """
    data = request.get_json(silent=True) or {}
    source_url = (data.get('url') or '').strip()
    custom_id  = (data.get('id') or '').strip() or None

    if not source_url:
        return jsonify({'error': 'Missing required field: url'}), 400

    valid, reason = validate_url(source_url)
    if not valid:
        return jsonify({'error': 'Invalid URL', 'message': reason}), 400

    client_ip = get_client_ip()
    transcoder = manager.create_stream(source_url, custom_id, client_ip)

    return jsonify(_build_stream_response(transcoder)), 201


# ---------------------------------------------------------------------------
# HLS Streaming
# ---------------------------------------------------------------------------

@api.route('/stream/<stream_id>/playlist.m3u8', methods=['GET'])
@handle_errors
def get_hls_playlist(stream_id: str):
    """
    Serve the HLS playlist (``.m3u8``) for a stream.

    Point any HLS-compatible player (hls.js, Video.js, Safari native) at
    this URL.  Segment filenames are rewritten to use the API segment
    endpoint so they are served through Flask rather than directly from disk.

    Returns ``application/vnd.apple.mpegurl``.
    """
    transcoder = manager.get_stream(stream_id)
    if not transcoder:
        return jsonify({'error': 'Stream not found', 'stream_id': stream_id}), 404

    transcoder.info.touch()

    # Wait up to 5 s for the first playlist to appear on a newly started stream.
    if not transcoder.has_playlist():
        for _ in range(10):
            time.sleep(0.5)
            if transcoder.has_playlist():
                break
        else:
            return jsonify({
                'error': 'Playlist not yet available',
                'message': 'Stream is still starting up, try again shortly',
                'stream_id': stream_id,
            }), 503

    playlist = transcoder.get_playlist()
    if not playlist:
        return jsonify({'error': 'Failed to read playlist', 'stream_id': stream_id}), 500

    rewritten = _rewrite_playlist_paths(playlist, stream_id)

    return Response(
        rewritten,
        mimetype='application/vnd.apple.mpegurl',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'Access-Control-Allow-Origin': '*',
            'X-Stream-ID': stream_id,
        },
    )


@api.route('/stream/<stream_id>/segments/<filename>', methods=['GET'])
@handle_errors
def get_hls_segment(stream_id: str, filename: str):
    """
    Serve an HLS segment file (``.ts``) for a stream.

    Segment URLs are embedded in the playlist by ``_rewrite_playlist_paths``
    and fetched automatically by HLS players.

    Returns ``video/mp2t``.
    """
    transcoder = manager.get_stream(stream_id)
    if not transcoder:
        return jsonify({'error': 'Stream not found', 'stream_id': stream_id}), 404

    transcoder.info.touch()
    transcoder.register_client_access()

    segment_path = transcoder.get_segment_path(filename)
    if not segment_path:
        return jsonify({'error': 'Segment not found', 'filename': filename}), 404

    return send_file(segment_path, mimetype='video/mp2t', as_attachment=False)


def _rewrite_playlist_paths(playlist: str, stream_id: str) -> str:
    """
    Rewrite segment filenames in a playlist to use the API segment endpoint.

    FFmpeg writes bare filenames (e.g. ``segment_00001.ts``); clients need
    fully-qualified API URLs.

    Args:
        playlist:  Raw ``.m3u8`` content.
        stream_id: Stream identifier for URL construction.

    Returns:
        Playlist with segment lines replaced by ``/api/stream/<id>/segments/<file>``.
    """
    lines = playlist.split('\n')
    rewritten = []

    for line in lines:
        stripped = line.strip()
        # Non-empty lines that do not start with '#' are segment references.
        if stripped and not stripped.startswith('#'):
            filename = os.path.basename(stripped)
            rewritten.append(f"/api/stream/{stream_id}/segments/{filename}")
        else:
            rewritten.append(line)

    return '\n'.join(rewritten)


# ---------------------------------------------------------------------------
# Stream Status and Control
# ---------------------------------------------------------------------------

@api.route('/stream/<stream_id>', methods=['GET'])
@handle_errors
def get_stream_by_id(stream_id: str):
    """Return stream information and HLS URL."""
    transcoder = manager.get_stream(stream_id)
    if not transcoder:
        return jsonify({'error': 'Stream not found', 'stream_id': stream_id}), 404

    return jsonify({
        'stream_id': stream_id,
        'status': transcoder.info.status.name,
        'is_alive': transcoder.is_alive,
        'hls_url': f"/api/stream/{stream_id}/playlist.m3u8",
        'smart_transcoding': transcoder.info.is_smart_transcoding,
        'codecs': transcoder.info.codec_info.to_dict(),
        'restart_count': transcoder.restart_count,
    })


@api.route('/stream/<stream_id>', methods=['DELETE'])
@handle_errors
@require_auth
def delete_stream(stream_id: str):
    """Stop and remove a stream."""
    if manager.stop_stream(stream_id):
        return jsonify({'success': True, 'message': f'Stream {stream_id} stopped'})
    return jsonify({'error': 'Stream not found', 'stream_id': stream_id}), 404


@api.route('/stream/<stream_id>/status', methods=['GET'])
@handle_errors
def get_stream_status(stream_id: str):
    """Return detailed status of a specific stream."""
    transcoder = manager.get_stream(stream_id)
    if not transcoder:
        return jsonify({'error': 'Stream not found', 'stream_id': stream_id}), 404

    return jsonify(transcoder.get_status())


# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------

@api.route('/streams', methods=['GET'])
def list_streams():
    """List all active streams."""
    streams = manager.list_streams()
    return jsonify({'count': len(streams), 'streams': streams})


@api.route('/streams/stop-all', methods=['POST'])
@handle_errors
@require_auth
def stop_all_streams():
    """Stop all active transcoding streams."""
    count = manager.stop_all()
    return jsonify({
        'success': True,
        'message': f'Stopped {count} stream(s)',
        'count': count,
    })


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

@api.route('/probe', methods=['GET', 'POST'])
@handle_errors
def probe_stream():
    """
    Probe a stream URL to detect codec and metadata information.

    Accepts ``url`` as a query parameter (GET) or a JSON body field (POST).
    Uses a lightweight one-shot probe that does not register a stream with
    the manager and does not create any output directories.

    Returns JSON with codec info and smart-transcode eligibility.
    """
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        source_url = (data.get('url') or '').strip()
    else:
        source_url = request.args.get('url', '').strip()

    if not source_url:
        return jsonify({'error': 'Missing required parameter: url'}), 400

    valid, reason = validate_url(source_url)
    if not valid:
        return jsonify({'error': 'Invalid URL', 'message': reason}), 400

    # Import here to keep the module-level import surface clean and avoid
    # any circular-import risk at startup.
    from transcoder.transcoder import StreamTranscoder

    # Use a temporary transcoder for probing only.  The stream_id carries a
    # "probe_" prefix so orphaned-segment cleanup in the manager ignores it,
    # and the output_dir is never created because we never call start().
    probe_id = f"probe_{int(time.time() * 1000)}"
    transcoder = StreamTranscoder(source_url, probe_id)
    result = transcoder.probe()

    if not result.success:
        return jsonify({
            'success': False,
            'url': source_url,
            'error': result.error_message,
        }), 400

    can_copy = (
        result.codec_info.can_copy_video(config.video.copyable_codecs)
        if result.codec_info else False
    )

    return jsonify({
        'success': True,
        'url': source_url,
        'codecs': result.codec_info.to_dict() if result.codec_info else None,
        'metadata': result.metadata.to_dict() if result.metadata else None,
        'can_smart_transcode': can_copy,
    })