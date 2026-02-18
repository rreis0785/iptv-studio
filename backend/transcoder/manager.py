"""
Stream manager for handling multiple concurrent transcoding streams.

This module provides thread-safe management of multiple StreamTranscoder
instances, including lifecycle management, cleanup, and resource limits.
"""

import atexit
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from transcoder.config import config
from transcoder.models import StreamInfo, StreamStatus
from transcoder.transcoder import StreamTranscoder

logger = logging.getLogger(__name__)


class StreamManager:
    """
    Thread-safe manager for multiple concurrent transcoding streams.
    
    Features:
    - Create, track, and cleanup streams
    - Enforce resource limits (max concurrent, per-IP limits)
    - Automatic cleanup of idle/dead streams
    - HLS segment directory management
    - Health monitoring
    
    Usage:
        manager = StreamManager()
        manager.start_cleanup_thread()
        
        # Create a stream
        transcoder = manager.create_stream("http://example.com/stream.ts")
        
        # Get existing stream
        transcoder = manager.get_stream("stream_001")
        
        # Stop a stream
        manager.stop_stream("stream_001")
        
        # Cleanup on shutdown
        manager.stop_all()
    """
    
    def __init__(self):
        """Initialize the stream manager."""
        self._streams: Dict[str, StreamTranscoder] = {}
        self._lock = threading.RLock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_running = False
        self._stream_counter = 0
        
        # Metrics
        self._total_streams_created = 0
        self._total_errors = 0
        
        # Ensure HLS base directory exists
        os.makedirs(config.hls.segment_dir, exist_ok=True)
        
        # Register shutdown handler
        atexit.register(self.stop_all)
    
    # -------------------------------------------------------------------------
    # Stream Creation
    # -------------------------------------------------------------------------
    
    def create_stream(
        self,
        source_url: str,
        stream_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        start: bool = True,
    ) -> Optional[StreamTranscoder]:
        """
        Create a new transcoding stream.
        
        Args:
            source_url: URL of the source stream
            stream_id: Optional custom stream ID (auto-generated if not provided)
            client_ip: Client IP for per-IP rate limiting
            start: If True, start transcoding immediately
            
        Returns:
            StreamTranscoder instance, or None if creation failed
            
        Raises:
            ValueError: If resource limits would be exceeded
        """
        with self._lock:
            # Check resource limits
            if len(self._streams) >= config.stream.max_concurrent:
                raise ValueError(
                    f"Maximum concurrent streams reached ({config.stream.max_concurrent})"
                )
            
            # Check per-IP limit
            if client_ip:
                ip_count = sum(
                    1 for s in self._streams.values()
                    if getattr(s, 'client_ip', None) == client_ip
                )
                if ip_count >= config.stream.max_per_ip:
                    raise ValueError(
                        f"Maximum streams per IP reached ({config.stream.max_per_ip})"
                    )
            
            # Generate stream ID if not provided
            if not stream_id:
                self._stream_counter += 1
                stream_id = f"stream_{int(time.time())}_{self._stream_counter:04d}"
            
            # Check if stream ID already exists
            if stream_id in self._streams:
                raise ValueError(f"Stream ID already exists: {stream_id}")
            
            # Create transcoder
            transcoder = StreamTranscoder(source_url, stream_id)
            if client_ip:
                transcoder.client_ip = client_ip  # type: ignore
            
            # Start if requested
            if start:
                if not transcoder.start():
                    self._total_errors += 1
                    return None
            
            # Track the stream
            self._streams[stream_id] = transcoder
            self._total_streams_created += 1
            
            logger.info(
                f"Created stream {stream_id} "
                f"(total active: {len(self._streams)})"
            )
            
            return transcoder
    
    def get_stream(self, stream_id: str) -> Optional[StreamTranscoder]:
        """
        Get an existing stream by ID.
        
        Args:
            stream_id: The stream identifier
            
        Returns:
            StreamTranscoder if found, None otherwise
        """
        with self._lock:
            return self._streams.get(stream_id)
    
    def get_or_create_stream(
        self,
        source_url: str,
        stream_id: Optional[str] = None,
        **kwargs,
    ) -> Optional[StreamTranscoder]:
        """
        Get an existing stream or create a new one.
        
        If a stream with the given ID exists and is healthy, returns it.
        Otherwise creates a new stream.
        
        Args:
            source_url: URL of the source stream
            stream_id: Optional stream ID
            **kwargs: Additional arguments for create_stream
            
        Returns:
            StreamTranscoder instance or None
        """
        with self._lock:
            if stream_id and stream_id in self._streams:
                transcoder = self._streams[stream_id]
                if transcoder.is_alive:
                    transcoder.info.touch()
                    return transcoder
                else:
                    # Remove dead stream
                    self._remove_stream(stream_id)
            
            return self.create_stream(source_url, stream_id, **kwargs)
    
    # -------------------------------------------------------------------------
    # Stream Lifecycle
    # -------------------------------------------------------------------------
    
    def stop_stream(self, stream_id: str) -> bool:
        """
        Stop and remove a stream.
        
        Args:
            stream_id: The stream to stop
            
        Returns:
            True if stream was found and stopped
        """
        with self._lock:
            transcoder = self._streams.get(stream_id)
            if not transcoder:
                return False
            
            transcoder.stop()
            del self._streams[stream_id]
            
            logger.info(
                f"Stopped stream {stream_id} "
                f"(remaining: {len(self._streams)})"
            )
            return True
    
    def _remove_stream(self, stream_id: str) -> None:
        """Remove a stream without stopping (for already-dead streams)."""
        if stream_id in self._streams:
            # Clean up output directory
            transcoder = self._streams[stream_id]
            transcoder._cleanup_output_dir()
            del self._streams[stream_id]
    
    def stop_all(self) -> int:
        """
        Stop all active streams.
        
        Called automatically on shutdown via atexit.
        
        Returns:
            Number of streams stopped
        """
        with self._lock:
            count = len(self._streams)
            
            if count == 0:
                return 0
            
            logger.info(f"Stopping all streams ({count})")
            
            for stream_id, transcoder in list(self._streams.items()):
                try:
                    transcoder.stop()
                except Exception as e:
                    logger.error(f"Error stopping {stream_id}: {e}")
            
            self._streams.clear()
            logger.info(f"Stopped {count} stream(s)")
            
            return count
    
    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    
    def start_cleanup_thread(self) -> None:
        """Start background thread for automatic cleanup of dead/idle streams."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        
        self._cleanup_running = True
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="stream-cleanup",
            daemon=True,
        )
        self._cleanup_thread.start()
        logger.info("Started cleanup thread")
    
    def stop_cleanup_thread(self) -> None:
        """Stop the cleanup background thread."""
        self._cleanup_running = False
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None
    
    def _cleanup_loop(self) -> None:
        """Background loop that periodically cleans up streams."""
        while self._cleanup_running:
            try:
                self.cleanup_dead_streams()
                self.cleanup_idle_streams()
                self.cleanup_orphaned_segments()
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            
            time.sleep(config.stream.cleanup_interval)
    
    def cleanup_dead_streams(self) -> int:
        """
        Remove streams that have permanently died (exhausted retries).
        
        Streams with auto-restart enabled will restart themselves via
        the health monitor thread. This only cleans up streams that
        are truly dead (in ERROR or STOPPED state).
        
        Returns:
            Number of dead streams removed
        """
        removed = 0
        
        with self._lock:
            for stream_id, transcoder in list(self._streams.items()):
                # Only remove streams in terminal states
                # (auto-restart handles transient failures)
                if transcoder.info.status.is_terminal() and not transcoder.is_alive:
                    logger.info(f"Cleaning up dead stream: {stream_id}")
                    transcoder.stop()  # Ensure cleanup
                    del self._streams[stream_id]
                    removed += 1
        
        if removed:
            logger.info(f"Cleaned up {removed} dead stream(s)")
        
        return removed
    
    def cleanup_idle_streams(self) -> int:
        """
        Remove streams that have been idle too long.
        
        A stream is considered idle if it has no clients and hasn't
        been accessed within the idle timeout period.
        
        Returns:
            Number of idle streams removed
        """
        removed = 0
        now = datetime.now(timezone.utc)
        idle_threshold = config.stream.idle_timeout
        
        with self._lock:
            for stream_id, transcoder in list(self._streams.items()):
                # Skip streams with active clients
                if transcoder.info.client_count > 0:
                    continue
                
                # Check idle time
                idle_seconds = (now - transcoder.info.last_accessed).total_seconds()
                
                if idle_seconds > idle_threshold:
                    logger.info(
                        f"Cleaning up idle stream: {stream_id} "
                        f"(idle for {idle_seconds:.0f}s)"
                    )
                    transcoder.stop()
                    del self._streams[stream_id]
                    removed += 1
        
        if removed:
            logger.info(f"Cleaned up {removed} idle stream(s)")
        
        return removed
    
    def cleanup_orphaned_segments(self) -> int:
        """
        Remove orphaned HLS segment directories.
        
        Cleans up directories in the HLS segment dir that don't
        correspond to any active stream (e.g., from crashes).
        
        Returns:
            Number of orphaned directories removed
        """
        removed = 0
        segment_dir = config.hls.segment_dir
        
        if not os.path.exists(segment_dir):
            return 0
        
        try:
            with self._lock:
                active_ids = set(self._streams.keys())
            
            for dirname in os.listdir(segment_dir):
                dir_path = os.path.join(segment_dir, dirname)
                if os.path.isdir(dir_path) and dirname not in active_ids:
                    try:
                        shutil.rmtree(dir_path, ignore_errors=True)
                        removed += 1
                        logger.debug(f"Cleaned up orphaned segment dir: {dirname}")
                    except Exception as e:
                        logger.error(f"Error cleaning orphaned dir {dirname}: {e}")
        except Exception as e:
            logger.error(f"Error scanning segment directory: {e}")
        
        if removed:
            logger.info(f"Cleaned up {removed} orphaned segment dir(s)")
        
        return removed
    
    # -------------------------------------------------------------------------
    # Status and Metrics
    # -------------------------------------------------------------------------
    
    def list_streams(self) -> List[Dict[str, Any]]:
        """
        List all active streams with their status.
        
        Returns:
            List of stream status dictionaries
        """
        with self._lock:
            return [
                transcoder.get_status()
                for transcoder in self._streams.values()
            ]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get manager-level statistics.
        
        Returns:
            Dictionary with aggregate statistics
        """
        with self._lock:
            active = len(self._streams)
            running = sum(1 for s in self._streams.values() if s.is_alive)
            total_clients = sum(
                s.info.client_count for s in self._streams.values()
            )
            total_bytes = sum(
                s.info.stats.bytes_sent for s in self._streams.values()
            )
            total_restarts = sum(
                s.restart_count for s in self._streams.values()
            )
            
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
        """Get number of active streams."""
        with self._lock:
            return len(self._streams)
    
    def __len__(self) -> int:
        """Return number of managed streams."""
        return self.active_count
    
    def __contains__(self, stream_id: str) -> bool:
        """Check if stream ID exists."""
        with self._lock:
            return stream_id in self._streams
    
    def __repr__(self) -> str:
        return f"StreamManager(streams={self.active_count})"


# Global manager instance
manager = StreamManager()