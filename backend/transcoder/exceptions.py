"""
Custom exceptions for the transcoding server.

This module defines application-specific exceptions for better
error handling and reporting.
"""


class TranscoderError(Exception):
    """Base exception for all transcoder errors."""
    
    def __init__(self, message: str, stream_id: str = None):
        super().__init__(message)
        self.message = message
        self.stream_id = stream_id
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        result = {'error': self.__class__.__name__, 'message': self.message}
        if self.stream_id:
            result['stream_id'] = self.stream_id
        return result


class FFmpegError(TranscoderError):
    """Error related to FFmpeg execution."""
    
    def __init__(
        self,
        message: str,
        stream_id: str = None,
        exit_code: int = None,
        stderr: str = None,
    ):
        super().__init__(message, stream_id)
        self.exit_code = exit_code
        self.stderr = stderr
    
    def to_dict(self) -> dict:
        result = super().to_dict()
        if self.exit_code is not None:
            result['exit_code'] = self.exit_code
        if self.stderr:
            result['stderr'] = self.stderr[:500]  # Limit length
        return result


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg binary not found."""
    
    def __init__(self, path: str = 'ffmpeg'):
        super().__init__(
            f"FFmpeg not found at: {path}. "
            "Please install FFmpeg and ensure it's in your PATH."
        )
        self.path = path


class ProbeError(TranscoderError):
    """Error during stream probing."""
    pass


class ProbeTimeoutError(ProbeError):
    """Stream probe timed out."""
    
    def __init__(self, url: str, timeout: int):
        super().__init__(f"Probe timed out after {timeout}s for: {url}")
        self.url = url
        self.timeout = timeout


class StreamError(TranscoderError):
    """Error related to stream management."""
    pass


class StreamNotFoundError(StreamError):
    """Requested stream not found."""
    
    def __init__(self, stream_id: str):
        super().__init__(f"Stream not found: {stream_id}", stream_id)


class StreamAlreadyExistsError(StreamError):
    """Stream with given ID already exists."""
    
    def __init__(self, stream_id: str):
        super().__init__(f"Stream already exists: {stream_id}", stream_id)


class ResourceLimitError(StreamError):
    """Resource limit exceeded."""
    pass


class MaxStreamsError(ResourceLimitError):
    """Maximum concurrent streams reached."""
    
    def __init__(self, current: int, maximum: int):
        super().__init__(
            f"Maximum concurrent streams reached ({current}/{maximum})"
        )
        self.current = current
        self.maximum = maximum


class MaxStreamsPerIPError(ResourceLimitError):
    """Maximum streams per IP reached."""
    
    def __init__(self, ip: str, current: int, maximum: int):
        super().__init__(
            f"Maximum streams per IP reached for {ip} ({current}/{maximum})"
        )
        self.ip = ip
        self.current = current
        self.maximum = maximum


class InvalidURLError(TranscoderError):
    """Invalid stream URL."""
    
    def __init__(self, url: str, reason: str = None):
        message = f"Invalid URL: {url}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)
        self.url = url
        self.reason = reason