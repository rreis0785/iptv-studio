"""
Stream manager for handling multiple concurrent transcoding streams.

This module provides thread-safe management of multiple StreamTranscoder
instances, including lifecycle management, cleanup, and resource limits.
"""

import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from transcoder.config import config
from transcoder.exceptions import (
    MaxStreamsError,
    MaxStreamsPerIPError,
    StreamAlreadyExistsError,
    StreamNotFoundError,
)
from transcoder.models import StreamStatus
from transcoder.transcoder import StreamTranscoder
from transcoder.utils import generate_stream_id

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Thread-safe manager for multiple concurrent transcoding streams.

    Features:
    - Create, track, and stop streams
    - Enforce resource limits (max concurrent, per-IP)
    - Automatic cleanup of idle and dead streams
    - Orphaned HLS segment directory recovery
    - Health monitoring

    Locking contract
    ----------------
    ``_lock`` guards ``_streams`` and the counters ``_total_streams_created``
    and ``_total_errors``.  It is *never* held while calling
    ``transcoder.start()`` — probing a stream can take up to
    ``probe_timeout`` seconds and must not block reads or other creates.

    Usage::

        manager = StreamManager()
        manager.start_cleanup_thread()

        transcoder = manager.create_stream("http://example.com/stream.ts")
        transcoder = manager.get_stream("stream_001")
        manager.stop_stream("stream_001")
        manager.stop_all()
    """

    def __init__(self):
        self._streams: Dict[str, StreamTranscoder] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_running = False

        # Lifetime metrics
        self._total_streams_created: int = 0
        self._total_errors: int = 0

        # Ensure the HLS base directory exists at startup
        os.makedirs(config.hls.segment_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Stream Creation
    # -------------------------------------------------------------------------

    def create_stream(
        self,
        source_url: str,
        stream_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        start: bool = True,
    ) -> StreamTranscoder:
        """
        Create a new transcoding stream.

        Resource checks and stream registration happen under the lock.
        ``transcoder.start()`` (which includes probing) runs *outside* the
        lock so slow probe calls do not stall unrelated operations.

        Args:
            source_url: URL of the source stream.
            stream_id:  Optional custom stream ID (auto-generated if omitted).
            client_ip:  Client IP for per-IP rate limiting.
            start:      If True, start transcoding immediately.

        Returns:
            The created ``StreamTranscoder`` instance.

        Raises:
            MaxStreamsError:        Global concurrent stream limit reached.
            MaxStreamsPerIPError:   Per-IP stream limit reached.
            StreamAlreadyExistsError: ``stream_id`` is already in use.
            RuntimeError:           FFmpeg failed to start (if ``start=True``).
        """
        # --- resource checks and registration (brief lock window) ---
        with self._lock:
            active = len(self._streams)
            if active >= config.stream.max_concurrent:
                raise MaxStreamsError(active, config.stream.max_concurrent)

            if client_ip:
                ip_count = sum(
                    1 for s in self._streams.values()
                    if s.client_ip == client_ip
                )
                if ip_count >= config.stream.max_per_ip:
                    raise MaxStreamsPerIPError(
                        client_ip, ip_count, config.stream.max_per_ip
                    )

            if not stream_id:
                stream_id = generate_stream_id(source_url)

            if stream_id in self._streams:
                raise StreamAlreadyExistsError(stream_id)

            # Register before start so the ID is reserved even while probing.
            transcoder = StreamTranscoder(source_url, stream_id, client_ip)
            self._streams[stream_id] = transcoder
            self._total_streams_created += 1

        logger.info(
            "Created stream %s (active: %d)", stream_id, self.active_count
        )

        # --- start outside the lock ---
        if start:
            if not transcoder.start():
                # Remove the reservation and surface a clear error.
                with self._lock:
                    self._streams.pop(stream_id, None)
                    self._total_errors += 1
                raise RuntimeError(
                    f"Failed to start stream {stream_id}: "
                    f"{transcoder.info.error_message or 'unknown error'}"
                )

        return transcoder

    def get_stream(self, stream_id: str) -> Optional[StreamTranscoder]:
        """
        Return an existing stream by ID, or None if not found.

        Args:
            stream_id: The stream identifier.
        """
        with self._lock:
            return self._streams.get(stream_id)

    def get_or_create_stream(
        self,
        source_url: str,
        stream_id: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> StreamTranscoder:
        """
        Return a healthy existing stream or create a new one.

        If a stream matching ``stream_id`` exists and its FFmpeg process is
        alive, it is returned immediately.  Dead streams are evicted first.

        Args:
            source_url: URL of the source stream.
            stream_id:  Optional stream ID to look up or assign.
            client_ip:  Client IP for rate limiting on creation.

        Returns:
            A running ``StreamTranscoder`` instance.

        Raises:
            Same exceptions as ``create_stream``.
        """
        if stream_id:
            with self._lock:
                existing = self._streams.get(stream_id)
                if existing is not None:
                    if existing.is_alive:
                        existing.info.touch()
                        return existing
                    # Dead stream — evict before creating a replacement
                    self._evict_stream(stream_id)

        return self.create_stream(source_url, stream_id, client_ip)

    # -------------------------------------------------------------------------
    # Stream Lifecycle
    # -------------------------------------------------------------------------

    def stop_stream(self, stream_id: str) -> bool:
        """
        Stop and remove a stream.

        Args:
            stream_id: The stream to stop.

        Returns:
            True if the stream was found and stopped, False otherwise.
        """
        with self._lock:
            transcoder = self._streams.get(stream_id)
            if not transcoder:
                return False
            del self._streams[stream_id]

        # Stop outside the lock — involves subprocess wait.
        transcoder.stop()
        logger.info(
            "Stopped stream %s (remaining: %d)", stream_id, self.active_count
        )
        return True

    def stop_all(self) -> int:
        """
        Stop all active streams.

        Safe to call multiple times (idempotent).

        Returns:
            Number of streams that were stopped.
        """
        with self._lock:
            if not self._streams:
                return 0
            snapshot = dict(self._streams)
            self._streams.clear()

        count = len(snapshot)
        logger.info("Stopping all streams (%d)", count)

        for stream_id, transcoder in snapshot.items():
            try:
                transcoder.stop()
            except Exception as exc:
                logger.error("Error stopping %s: %s", stream_id, exc)

        logger.info("Stopped %d stream(s)", count)
        return count

    def _evict_stream(self, stream_id: str) -> None:
        """
        Remove a stream entry and clean up its segment directory.

        Must be called while holding ``_lock``.  Uses the public
        ``cleanup()`` method on the transcoder rather than accessing
        private internals.
        """
        transcoder = self._streams.pop(stream_id, None)
        if transcoder is not None:
            transcoder.cleanup()

    # -------------------------------------------------------------------------
    # Cleanup Thread
    # -------------------------------------------------------------------------

    def start_cleanup_thread(self) -> None:
        """Start the background cleanup thread (idempotent)."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return

        self._cleanup_running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="stream-cleanup",
            daemon=True,
        )
        self._cleanup_thread.start()
        logger.info("Cleanup thread started")

    def stop_cleanup_thread(self) -> None:
        """Signal and join the cleanup thread."""
        self._cleanup_running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None

    def _cleanup_loop(self) -> None:
        """Periodic cleanup loop running in the background thread."""
        while self._cleanup_running:
            try:
                self.cleanup_dead_streams()
                self.cleanup_idle_streams()
                self.cleanup_orphaned_segments()
            except Exception as exc:
                logger.error("Cleanup error: %s", exc)

            time.sleep(config.stream.cleanup_interval)

    # -------------------------------------------------------------------------
    # Cleanup Operations (also callable directly for testing / admin)
    # -------------------------------------------------------------------------

    def cleanup_dead_streams(self) -> int:
        """
        Remove streams that have permanently died (exhausted auto-retries).

        Streams in a transient error state that still have ``_should_run``
        set are left alone — the health monitor will restart them.

        Returns:
            Number of dead streams removed.
        """
        removed = 0

        with self._lock:
            dead = [
                sid for sid, t in self._streams.items()
                if t.info.status.is_terminal() and not t.is_alive
            ]

        for stream_id in dead:
            with self._lock:
                transcoder = self._streams.pop(stream_id, None)
            if transcoder:
                transcoder.stop()   # ensures cleanup() is called
                removed += 1
                logger.info("Cleaned up dead stream: %s", stream_id)

        if removed:
            logger.info("Removed %d dead stream(s)", removed)
        return removed

    def cleanup_idle_streams(self) -> int:
        """
        Remove streams that have had no client access within the idle timeout.

        Streams with active clients (``client_count > 0``) are never evicted.

        Returns:
            Number of idle streams removed.
        """
        removed = 0
        now = datetime.now(timezone.utc)
        idle_threshold = config.stream.idle_timeout

        with self._lock:
            idle = [
                (sid, t) for sid, t in self._streams.items()
                if t.info.client_count == 0
                and (now - t.info.last_accessed).total_seconds() > idle_threshold
            ]

        for stream_id, transcoder in idle:
            with self._lock:
                # Re-check inside the lock — client may have connected
                # between snapshot and now.
                t = self._streams.get(stream_id)
                if t is None:
                    continue
                idle_secs = (now - t.info.last_accessed).total_seconds()
                if t.info.client_count > 0 or idle_secs <= idle_threshold:
                    continue
                del self._streams[stream_id]

            transcoder.stop()
            removed += 1
            logger.info(
                "Cleaned up idle stream: %s (idle %.0fs)", stream_id, idle_secs
            )

        if removed:
            logger.info("Removed %d idle stream(s)", removed)
        return removed

    def cleanup_orphaned_segments(self) -> int:
        """
        Remove HLS segment directories not belonging to any active stream.

        Handles leftover directories from server crashes or incomplete
        shutdowns.

        Returns:
            Number of orphaned directories removed.
        """
        segment_dir = config.hls.segment_dir
        if not os.path.exists(segment_dir):
            return 0

        removed = 0

        try:
            # Snapshot active IDs *before* the filesystem scan so streams
            # created during the scan are not mistakenly treated as orphans.
            with self._lock:
                active_ids = set(self._streams.keys())

            for dirname in os.listdir(segment_dir):
                if dirname in active_ids:
                    continue
                dir_path = os.path.join(segment_dir, dirname)
                if not os.path.isdir(dir_path):
                    continue
                try:
                    shutil.rmtree(dir_path, ignore_errors=True)
                    removed += 1
                    logger.debug("Removed orphaned segment dir: %s", dirname)
                except Exception as exc:
                    logger.error(
                        "Error removing orphaned dir %s: %s", dirname, exc
                    )

        except Exception as exc:
            logger.error("Error scanning segment directory: %s", exc)

        if removed:
            logger.info("Removed %d orphaned segment dir(s)", removed)
        return removed

    # -------------------------------------------------------------------------
    # Status and Metrics
    # -------------------------------------------------------------------------

    def list_streams(self) -> List[Dict[str, Any]]:
        """Return a status snapshot of all active streams."""
        with self._lock:
            transcoders = list(self._streams.values())
        return [t.get_status() for t in transcoders]

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate manager-level statistics."""
        with self._lock:
            streams = list(self._streams.values())

        active       = len(streams)
        running      = sum(1 for s in streams if s.is_alive)
        total_clients = sum(s.info.client_count for s in streams)
        total_bytes  = sum(s.info.stats.bytes_sent for s in streams)
        total_restarts = sum(s.restart_count for s in streams)

        return {
            'active_streams': active,
            'running_streams': running,
            'total_clients': total_clients,
            'total_bytes_sent': total_bytes,
            'total_restarts': total_restarts,
            'total_streams_created': self._total_streams_created,
            'total_errors': self._total_errors,
            'max_concurrent': config.stream.max_concurrent,
        }

    @property
    def active_count(self) -> int:
        """Number of currently tracked streams."""
        with self._lock:
            return len(self._streams)

    def __len__(self) -> int:
        return self.active_count

    def __contains__(self, stream_id: str) -> bool:
        with self._lock:
            return stream_id in self._streams

    def __repr__(self) -> str:
        return f"StreamManager(streams={self.active_count})"


# Global singleton — import this, not StreamManager directly.
manager = StreamManager()