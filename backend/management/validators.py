"""
Input validation utilities for the management API.

Provides URL validation, required field checking, and type validation.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from management.config import config

logger = logging.getLogger(__name__)


# Fields managed exclusively by the server — never accepted from API clients.
_READONLY_FIELDS = frozenset({'id', 'created_at', 'updated_at'})


def strip_readonly_fields(data: dict) -> dict:
    """
    Remove system-managed fields from user-submitted request data.

    Prevents callers from overriding auto-generated IDs or timestamps.
    """
    return {k: v for k, v in data.items() if k not in _READONLY_FIELDS}


def validate_url(url: str) -> Optional[str]:
    """
    Validate a stream URL.
    
    Args:
        url: URL to validate
        
    Returns:
        Error message if invalid, None if valid
    """
    if not url or not url.strip():
        return "URL cannot be empty"
    
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return f"Invalid URL format: {url}"
    
    if not parsed.scheme:
        return f"URL must include a protocol (e.g., http://): {url}"
    
    if parsed.scheme.lower() not in config.playlist.supported_protocols:
        allowed = ', '.join(config.playlist.supported_protocols)
        return f"Unsupported protocol '{parsed.scheme}'. Allowed: {allowed}"
    
    if not parsed.netloc:
        return f"URL must include a host: {url}"
    
    return None


def validate_required(data: dict, fields: List[str]) -> Optional[Dict[str, str]]:
    """
    Validate that required fields are present and non-empty.
    
    Args:
        data: Request data dictionary
        fields: List of required field names
        
    Returns:
        Dict with field -> error if any missing, None if all present
    """
    errors = {}
    for field in fields:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors[field] = f"{field} is required"
    
    return errors if errors else None


def validate_int_param(value: str, name: str, min_val: int = None, max_val: int = None) -> Tuple[Optional[int], Optional[str]]:
    """
    Validate and parse an integer query parameter.
    
    Args:
        value: Raw string value
        name: Parameter name (for error messages)
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)
        
    Returns:
        Tuple of (parsed_value, error_message)
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, f"{name} must be a valid integer"
    
    if min_val is not None and parsed < min_val:
        return None, f"{name} must be >= {min_val}"
    
    if max_val is not None and parsed > max_val:
        return None, f"{name} must be <= {max_val}"
    
    return parsed, None


def validate_string_length(value: str, name: str, max_length: int = 500) -> Optional[str]:
    """
    Validate string length.
    
    Args:
        value: String to validate
        name: Field name (for error messages)
        max_length: Maximum allowed length
        
    Returns:
        Error message if too long, None if valid
    """
    if value and len(value) > max_length:
        return f"{name} must be {max_length} characters or fewer"
    return None


def validate_channel_data(data: dict, require_all: bool = True) -> Optional[str]:
    """
    Validate channel creation/update data.
    
    Args:
        data: Channel data dict
        require_all: If True, require name/url/playlist_id
        
    Returns:
        Error message if invalid, None if valid
    """
    if require_all:
        errors = validate_required(data, ['name', 'url', 'playlist_id'])
        if errors:
            return next(iter(errors.values()))
    
    # Validate URL if provided
    if 'url' in data and data['url']:
        url_error = validate_url(data['url'])
        if url_error:
            return url_error
    
    # Validate name length
    if 'name' in data:
        name_error = validate_string_length(data['name'], 'name', 200)
        if name_error:
            return name_error
    
    return None


def validate_vod_data(data: dict, require_all: bool = True) -> Optional[str]:
    """
    Validate VOD creation/update data.
    
    Args:
        data: VOD data dict
        require_all: If True, require name/url/playlist_id
        
    Returns:
        Error message if invalid, None if valid
    """
    if require_all:
        errors = validate_required(data, ['name', 'url', 'playlist_id'])
        if errors:
            return next(iter(errors.values()))
    
    # Validate URL if provided
    if 'url' in data and data['url']:
        url_error = validate_url(data['url'])
        if url_error:
            return url_error
    
    # Validate numeric fields
    if 'duration' in data and data['duration'] is not None:
        if not isinstance(data['duration'], int) or data['duration'] < 0:
            return "duration must be a non-negative integer (seconds)"
    
    if 'year' in data and data['year'] is not None:
        if not isinstance(data['year'], int) or data['year'] < 1900 or data['year'] > 2100:
            return "year must be between 1900 and 2100"
    
    return None
