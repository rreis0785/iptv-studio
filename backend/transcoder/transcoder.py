"""
Stream transcoder implementation using FFmpeg.

This module contains the core transcoding logic that wraps FFmpeg
subprocess management with proper error handling, HLS output,
auto-restart resilience, and monitoring.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Generator, List, Optional, Tuple

from transcoder.config import config
from transcoder.models import (
    CodecInfo,
    ProbeResult,
    StreamInfo,
    StreamMetadata,
    StreamStatus,
)

logger = logging.getLogger(__name__)


class StreamTranscoder:
    """
    Manages an FFmpeg transcoding process for a single stream.

    Features:
    - HLS output for multi-client browser playback
    - Smart transcoding (copy H.264 video, transcode audio only)
    - Stream probing to detect codecs before transcoding
    - Auto-restart on failure with configurable retries
    - Low-latency configuration for live streaming
    - Real-time statistics monitoring

    Thread safety
    -------------
    ``_lock`` (RLock) guards ``process``, ``_stderr_buffer``,
    ``_restart_count``, and ``_should_run``.  Mutations to ``self.info``
    go through ``StreamInfo``'s own lock via its public methods
    (``touch()``, ``set_error()``).  Direct field writes on ``self.info``
    are performed only while holding both ``_lock`` and ``self.info._lock``.

    Usage::

        transcoder = StreamTranscoder("http://example.com/stream.ts", "stream_001")

        if transcoder.start():
            # Clients can now access:
            #   transcoder.playlist_path  -> HLS .m3u8 file
            #   transcoder.output_dir     -> directory with .ts segments
            pass

        transcoder.stop()

    Or with context manager::

        with StreamTranscoder(url, stream_id) as transcoder:
            # stream is running
            pass
    """

    def __init__(self, source_url: str, stream_id: str, client_ip: Optional[str] = None):
        """
        Initialise the transcoder.

        Args:
            source_url: URL of the source stream (HLS, MPEG-TS, RTMP, etc.)
            stream_id:  Unique identifier for this stream instance.
            client_ip:  Optional originating client IP (used by StreamManager
                        for per-IP rate limiting).
        """
        self.source_url = source_url
        self.stream_id = stream_id
        self.client_ip: Optional[str] = client_ip

        # Process management
        self.process: Optional[subprocess.Popen] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stderr_buffer: Deque[str] = deque(maxlen=config.ffmpeg.stderr_buffer_lines)
        self._lock = threading.RLock()

        # Auto-restart state
        self._restart_count: int = 0
        self._monitor_thread: Optional[threading.Thread] = None
        self._should_run: bool = False

        # HLS output directory
        self._output_dir = os.path.join(config.hls.segment_dir, stream_id)

        # Stream info
        self.info = StreamInfo(
            stream_id=stream_id,
            source_url=source_url,
        )

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def output_dir(self) -> str:
        """Get the HLS output directory path."""
        return self._output_dir

    @property
    def playlist_path(self) -> str:
        """Get the path to the HLS playlist file."""
        return os.path.join(self._output_dir, 'playlist.m3u8')

    @property
    def is_alive(self) -> bool:
        """Check if the FFmpeg process is still running."""
        return self.process is not None and self.process.poll() is None

    @property
    def stderr_output(self) -> List[str]:
        """Get a snapshot of buffered stderr output for debugging."""
        with self._lock:
            return list(self._stderr_buffer)

    @property
    def restart_count(self) -> int:
        """Get number of times the stream has been restarted."""
        with self._lock:
            return self._restart_count

    # -------------------------------------------------------------------------
    # Public cleanup (called by StreamManager — avoids cross-module private access)
    # -------------------------------------------------------------------------

    def cleanup(self) -> None:
        """
        Remove the HLS output directory and all segments.

        Safe to call multiple times; also called by ``stop()``.
        """
        self._cleanup_output_dir()

    # -------------------------------------------------------------------------
    # Stream Probing
    # -------------------------------------------------------------------------

    def probe(self) -> ProbeResult:
        """
        Probe the source stream to detect codecs and metadata.

        Uses ffprobe to analyse the stream without starting transcoding.
        This allows smart transcoding decisions (copy vs re-encode).

        Returns:
            ProbeResult with codec info, metadata, or error details.
        """
        with self.info._lock:
            self.info.status = StreamStatus.PROBING

        cmd = [
            config.ffmpeg.probe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-show_format',
            # probe_timeout is in seconds; ffprobe -timeout expects microseconds
            '-timeout', str(config.ffmpeg.probe_timeout * 1_000_000),
            self.source_url,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                # Add a small buffer over the ffprobe-level timeout so the
                # outer watchdog only fires if ffprobe itself ignores -timeout.
                timeout=config.ffmpeg.probe_timeout + 5,
            )

            if result.returncode != 0:
                error_msg = f"ffprobe failed: {result.stderr[:200]}"
                logger.error("[%s] %s", self.stream_id, error_msg)
                return ProbeResult(success=False, error_message=error_msg)

            data = json.loads(result.stdout)
            codec_info, metadata = self._parse_probe_data(data)

            # Resolve smart-transcode flag using the injected codec list so
            # CodecInfo has no dependency on config.
            is_smart = codec_info.can_copy_video(config.video.copyable_codecs)

            # Update stream info under its own lock.
            with self.info._lock:
                self.info.codec_info = codec_info
                self.info.metadata = metadata
                self.info.is_smart_transcoding = is_smart

            logger.info(
                "[%s] Probed: video=%s audio=%s smart_transcode=%s",
                self.stream_id,
                codec_info.video_codec,
                codec_info.audio_codec,
                is_smart,
            )

            return ProbeResult(
                success=True,
                codec_info=codec_info,
                metadata=metadata,
                raw_data=data,
            )

        except subprocess.TimeoutExpired:
            error_msg = (
                f"Stream probe timed out after {config.ffmpeg.probe_timeout}s"
            )
            logger.error("[%s] %s", self.stream_id, error_msg)
            return ProbeResult(success=False, error_message=error_msg)

        except json.JSONDecodeError as exc:
            error_msg = f"Failed to parse probe data: {exc}"
            logger.error("[%s] %s", self.stream_id, error_msg)
            return ProbeResult(success=False, error_message=error_msg)

        except Exception as exc:
            error_msg = f"Probe error: {exc}"
            logger.exception("[%s] %s", self.stream_id, error_msg)
            return ProbeResult(success=False, error_message=error_msg)

    def _parse_probe_data(self, data: Dict[str, Any]) -> Tuple[CodecInfo, StreamMetadata]:
        """
        Parse ffprobe JSON output into structured data.

        Only the first video and first audio stream are used.  Multi-audio
        (e.g. dual-language) streams are logged at DEBUG level rather than
        silently discarded.

        Args:
            data: Parsed JSON from ffprobe.

        Returns:
            Tuple of (CodecInfo, StreamMetadata).
        """
        codec_info = CodecInfo()
        metadata = StreamMetadata()

        streams = data.get('streams', [])
        audio_count = 0

        for stream in streams:
            codec_type = stream.get('codec_type')
            codec_name = stream.get('codec_name')

            if codec_type == 'video' and not codec_info.video_codec:
                codec_info.video_codec = codec_name
                codec_info.width = stream.get('width')
                codec_info.height = stream.get('height')
                codec_info.video_bitrate = int(stream.get('bit_rate', 0) or 0)

                # Frame rate is reported as "num/den" (e.g. "30000/1001")
                if fps_str := stream.get('r_frame_rate'):
                    try:
                        num, den = map(int, fps_str.split('/'))
                        codec_info.fps = round(num / den, 2) if den else 0.0
                    except (ValueError, ZeroDivisionError):
                        pass

            elif codec_type == 'audio':
                audio_count += 1
                if not codec_info.audio_codec:
                    codec_info.audio_codec = codec_name
                    codec_info.audio_bitrate = int(stream.get('bit_rate', 0) or 0)
                    codec_info.audio_channels = stream.get('channels')
                    codec_info.audio_sample_rate = int(
                        stream.get('sample_rate', 0) or 0
                    )
                else:
                    logger.debug(
                        "[%s] Additional audio stream ignored: codec=%s",
                        self.stream_id,
                        codec_name,
                    )

        if audio_count > 1:
            logger.debug(
                "[%s] Stream has %d audio tracks; only the first will be transcoded.",
                self.stream_id,
                audio_count,
            )

        # Container / format info
        fmt = data.get('format', {})
        codec_info.container = fmt.get('format_name')

        # Metadata tags
        tags = fmt.get('tags', {})
        metadata.title = tags.get('title')
        metadata.artist = tags.get('artist')
        metadata.album = tags.get('album')

        return codec_info, metadata

    # -------------------------------------------------------------------------
    # FFmpeg Command Building
    # -------------------------------------------------------------------------

    def _build_ffmpeg_command(self) -> List[str]:
        """
        Build the FFmpeg command for HLS output.

        Uses smart transcoding: copies video if H.264-compatible,
        always transcodes audio to AAC for browser compatibility.
        Outputs HLS segments to disk for multi-client access.

        Returns:
            List of command arguments for subprocess.
        """
        video_codec = (
            'copy' if self.info.is_smart_transcoding
            else config.video.fallback_codec
        )

        # read_timeout is in seconds; ffmpeg -timeout expects microseconds.
        read_timeout_us = config.ffmpeg.read_timeout * 1_000_000

        cmd = [
            config.ffmpeg.path,
            '-hide_banner',
            '-loglevel', config.ffmpeg.loglevel,

            # Reconnection options for live streams
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', str(config.ffmpeg.reconnect_delay_max),

            # Stall detection timeout
            '-timeout', str(read_timeout_us),

            # Input
            '-i', self.source_url,

            # Video
            '-c:v', video_codec,
        ]

        # Encoding options only needed when re-encoding
        if video_codec != 'copy':
            cmd.extend([
                '-preset', config.ffmpeg.preset,
                '-crf', str(config.ffmpeg.crf),
                '-tune', 'zerolatency',
                '-threads', str(config.ffmpeg.threads),
            ])

        # Audio: always transcode to AAC for browser compatibility
        cmd.extend([
            '-c:a', config.audio.codec,
            '-b:a', config.audio.bitrate,
            '-ar', config.audio.sample_rate,
            '-ac', str(config.audio.channels),
        ])

        # HLS muxer options
        cmd.extend([
            '-f', 'hls',
            '-hls_time', str(config.hls.segment_duration),
            '-hls_list_size', str(config.hls.playlist_size),
            '-hls_flags', 'delete_segments+append_list+independent_segments',
            '-hls_segment_type', config.hls.segment_format,
            '-hls_segment_filename', os.path.join(self._output_dir, 'segment_%05d.ts'),
            '-hls_allow_cache', '0',
            '-fflags', '+genpts',
            '-max_muxing_queue_size', '1024',
            self.playlist_path,
        ])

        return cmd

    # -------------------------------------------------------------------------
    # Process Management
    # -------------------------------------------------------------------------

    def start(self, probe_first: bool = True) -> bool:
        """
        Start the FFmpeg transcoding process.

        Probing runs *before* acquiring the main lock so the lock is not
        held during a potentially slow network operation.

        Args:
            probe_first: If True, probe the stream before starting (recommended).

        Returns:
            True if started successfully, False otherwise.
        """
        # Run probe outside the lock — it involves a subprocess call that can
        # take up to probe_timeout seconds and must not block other operations.
        if probe_first:
            probe_result = self.probe()
            if not probe_result.success:
                self.info.set_error(probe_result.error_message or "Probe failed")
                return False

        with self._lock:
            if self.process and self.process.poll() is None:
                logger.warning("[%s] Already running", self.stream_id)
                return True

            os.makedirs(self._output_dir, exist_ok=True)

            try:
                cmd = self._build_ffmpeg_command()
                logger.info("[%s] Starting FFmpeg: %s", self.stream_id, ' '.join(cmd))

                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,   # HLS writes to disk, not stdout
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )

                self._should_run = True

                with self.info._lock:
                    self.info.status = StreamStatus.RUNNING
                    self.info.started_at = datetime.now(timezone.utc)

                # stderr monitoring thread
                self._stderr_thread = threading.Thread(
                    target=self._monitor_stderr,
                    name=f"stderr-{self.stream_id}",
                    daemon=True,
                )
                self._stderr_thread.start()

                # Health / auto-restart monitor thread
                self._monitor_thread = threading.Thread(
                    target=self._health_monitor,
                    name=f"health-{self.stream_id}",
                    daemon=True,
                )
                self._monitor_thread.start()

                logger.info(
                    "[%s] Started (PID: %d)", self.stream_id, self.process.pid
                )
                return True

            except FileNotFoundError:
                error_msg = f"FFmpeg not found at: {config.ffmpeg.path}"
                logger.error("[%s] %s", self.stream_id, error_msg)
                self.info.set_error(error_msg)
                return False

            except Exception as exc:
                error_msg = f"Failed to start: {exc}"
                logger.exception("[%s] %s", self.stream_id, error_msg)
                self.info.set_error(error_msg)
                return False

    def _restart(self) -> bool:
        """
        Attempt to restart the FFmpeg process after a failure.

        Must be called from the health monitor thread only.

        Returns:
            True if the restart succeeded.
        """
        with self._lock:
            self._restart_count += 1

        self.info.stats.reconnects += 1

        logger.warning(
            "[%s] Restarting FFmpeg (attempt %d/%d)",
            self.stream_id,
            self._restart_count,
            config.ffmpeg.max_retries,
        )

        # Terminate the old process cleanly before relaunching.
        with self._lock:
            if self.process:
                try:
                    self.process.kill()
                    self.process.wait(timeout=3)
                except Exception as exc:
                    logger.warning(
                        "[%s] Error killing old process during restart: %s",
                        self.stream_id, exc,
                    )
                self.process = None

        try:
            cmd = self._build_ffmpeg_command()

            with self._lock:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )

            with self.info._lock:
                self.info.status = StreamStatus.RUNNING
                self.info.error_message = None

            # Restart stderr monitoring for the new process
            self._stderr_thread = threading.Thread(
                target=self._monitor_stderr,
                name=f"stderr-{self.stream_id}-r{self._restart_count}",
                daemon=True,
            )
            self._stderr_thread.start()

            logger.info(
                "[%s] Restarted (PID: %d)",
                self.stream_id,
                self.process.pid,
            )
            return True

        except Exception as exc:
            logger.error("[%s] Restart failed: %s", self.stream_id, exc)
            self.info.set_error(f"Restart failed: {exc}")
            return False

    def stop(self) -> None:
        """Stop the transcoding process and clean up all resources."""
        with self._lock:
            self._should_run = False

            if not self.process:
                self._cleanup_output_dir()
                return

            logger.info("[%s] Stopping", self.stream_id)

            try:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logger.warning("[%s] Force-killing process", self.stream_id)
                    self.process.kill()
                    self.process.wait()
            except Exception as exc:
                logger.error("[%s] Error during stop: %s", self.stream_id, exc)
            finally:
                self.process = None
                with self.info._lock:
                    self.info.status = StreamStatus.STOPPED
                self._cleanup_output_dir()
                logger.info("[%s] Stopped", self.stream_id)

    def _cleanup_output_dir(self) -> None:
        """Remove the HLS output directory and all segments."""
        try:
            if os.path.exists(self._output_dir):
                shutil.rmtree(self._output_dir, ignore_errors=True)
                logger.debug("[%s] Cleaned up output directory", self.stream_id)
        except Exception as exc:
            logger.error(
                "[%s] Error cleaning output dir: %s", self.stream_id, exc
            )

    # -------------------------------------------------------------------------
    # HLS File Access
    # -------------------------------------------------------------------------

    def get_playlist(self) -> Optional[str]:
        """
        Read the current HLS playlist content.

        Returns:
            Playlist content as a string, or None if not yet available.
        """
        try:
            if os.path.exists(self.playlist_path):
                with open(self.playlist_path, 'r') as f:
                    return f.read()
        except Exception as exc:
            logger.error("[%s] Error reading playlist: %s", self.stream_id, exc)
        return None

    def get_segment_path(self, filename: str) -> Optional[str]:
        """
        Return the full path to a segment file, or None if it does not exist.

        Prevents directory traversal by stripping any path components from
        the filename before constructing the full path.

        Args:
            filename: Segment filename (e.g. ``segment_00001.ts``).

        Returns:
            Absolute path if the file exists, None otherwise.
        """
        safe_name = os.path.basename(filename)
        path = os.path.join(self._output_dir, safe_name)
        return path if os.path.exists(path) else None

    def has_playlist(self) -> bool:
        """Return True if the HLS playlist file exists on disk."""
        return os.path.exists(self.playlist_path)

    def register_client_access(self) -> None:
        """
        Record a client segment fetch.

        Increments ``total_clients_served`` and ensures ``client_count``
        reflects at least one active client.  Thread-safe.
        """
        with self.info._lock:
            self.info.client_count = max(1, self.info.client_count)
            self.info.total_clients_served += 1

    # -------------------------------------------------------------------------
    # Legacy Streaming (backward compatibility)
    # -------------------------------------------------------------------------

    def stream_generator(self) -> Generator[bytes, None, None]:
        """
        Generator that yields transcoded stream chunks from FFmpeg stdout.

        .. deprecated::
            In HLS mode FFmpeg writes segments to disk (stdout is
            ``DEVNULL``).  This generator will yield nothing.  Use the HLS
            endpoints instead.  Kept only for backward compatibility.
        """
        with self.info._lock:
            self.info.client_count += 1
            self.info.total_clients_served += 1

        logger.info(
            "[%s] Legacy stream client connected (total: %d)",
            self.stream_id,
            self.info.client_count,
        )

        try:
            while self.is_alive:
                if not self.process or not self.process.stdout:
                    break
                try:
                    chunk = self.process.stdout.read(config.stream.buffer_size)
                    if chunk:
                        self.info.touch()
                        self.info.stats.bytes_sent += len(chunk)
                        yield chunk
                    else:
                        break
                except Exception as exc:
                    logger.debug("[%s] Stream read error: %s", self.stream_id, exc)
                    break

        except GeneratorExit:
            logger.debug("[%s] Legacy client generator closed", self.stream_id)

        finally:
            with self.info._lock:
                self.info.client_count -= 1
            logger.info(
                "[%s] Legacy client disconnected (remaining: %d)",
                self.stream_id,
                self.info.client_count,
            )

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    def _monitor_stderr(self) -> None:
        """
        Read and process FFmpeg stderr in a background thread.

        Appended to the deque buffer (bounded by ``stderr_buffer_lines``),
        and parses progress stats line by line.
        """
        if not self.process or not self.process.stderr:
            return

        try:
            for raw_line in self.process.stderr:
                decoded = raw_line.decode('utf-8', errors='replace').strip()
                if not decoded:
                    continue

                # deque is thread-safe for append / popleft with maxlen
                self._stderr_buffer.append(decoded)

                self._parse_ffmpeg_progress(decoded)

                line_lower = decoded.lower()
                if 'error' in line_lower:
                    logger.warning("[FFmpeg %s] %s", self.stream_id, decoded)
                    self.info.stats.errors += 1
                elif 'warning' in line_lower:
                    logger.debug("[FFmpeg %s] %s", self.stream_id, decoded)

        except Exception as exc:
            logger.error("[%s] Stderr monitor error: %s", self.stream_id, exc)

    def _health_monitor(self) -> None:
        """
        Monitor FFmpeg process health and trigger auto-restart on failure.

        Runs in a background daemon thread.  Checks the process every
        ``config.stream.health_poll_interval`` seconds and restarts up to
        ``config.ffmpeg.max_retries`` times using exponential backoff.
        """
        time.sleep(config.stream.health_startup_delay)

        while True:
            with self._lock:
                should_run = self._should_run
                restart_count = self._restart_count

            if not should_run:
                break

            if not self.is_alive:
                exit_code = self.process.returncode if self.process else None
                logger.warning(
                    "[%s] FFmpeg process died (exit code: %s)",
                    self.stream_id,
                    exit_code,
                )

                if restart_count < config.ffmpeg.max_retries:
                    # Linear back-off: delay grows with each attempt
                    delay = config.ffmpeg.retry_delay * (restart_count + 1)
                    logger.info(
                        "[%s] Waiting %.1fs before restart attempt %d/%d",
                        self.stream_id,
                        delay,
                        restart_count + 1,
                        config.ffmpeg.max_retries,
                    )
                    time.sleep(delay)

                    with self._lock:
                        still_wanted = self._should_run
                    if still_wanted and not self._restart():
                        logger.error(
                            "[%s] Restart failed, giving up", self.stream_id
                        )
                        self.info.set_error("Restart failed")
                        break
                else:
                    logger.error(
                        "[%s] Max retries (%d) exceeded, stopping",
                        self.stream_id,
                        config.ffmpeg.max_retries,
                    )
                    self.info.set_error("Max restart attempts exceeded")
                    break

            time.sleep(config.stream.health_poll_interval)

    def _parse_ffmpeg_progress(self, line: str) -> None:
        """
        Extract statistics from an FFmpeg progress output line.

        Args:
            line: A single decoded line of FFmpeg stderr output.
        """
        if match := re.search(r'frame=\s*(\d+)', line):
            self.info.stats.frames_processed = int(match.group(1))

        if match := re.search(r'bitrate=\s*([\d.]+)kbits/s', line):
            self.info.stats.current_bitrate = int(float(match.group(1)) * 1000)

        if match := re.search(r'\bfps=\s*([\d.]+)', line):
            self.info.stats.current_fps = float(match.group(1))

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return current status as a dictionary for API responses."""
        status = self.info.to_dict()
        with self._lock:
            status['restart_count'] = self._restart_count
        status['has_playlist'] = self.has_playlist()
        return status

    # -------------------------------------------------------------------------
    # Context Manager
    # -------------------------------------------------------------------------

    def __enter__(self) -> 'StreamTranscoder':
        """Context manager entry — starts transcoding."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit — ensures cleanup."""
        self.stop()

    def __repr__(self) -> str:
        return (
            f"StreamTranscoder("
            f"id={self.stream_id!r}, "
            f"status={self.info.status.name}, "
            f"restarts={self._restart_count})"
        )