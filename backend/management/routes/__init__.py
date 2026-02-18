"""
API Routes package.

Contains all Blueprint definitions for the IPTV API.
"""

import functools
import logging

from flask import jsonify, request

from management.config import config

logger = logging.getLogger(__name__)

# Blueprint imports
from management.routes.playlists import bp as playlists_bp
from management.routes.channels import bp as channels_bp
from management.routes.vod import bp as vod_bp
from management.routes.groups import bp as groups_bp
from management.routes.epg import bp as epg_bp
from management.routes.series import bp as series_bp
from management.routes.sources import bp as sources_bp

__all__ = [
    'playlists_bp',
    'channels_bp',
    'vod_bp',
    'groups_bp',
    'epg_bp',
    'series_bp',
    'sources_bp',
    'require_auth',
]


def require_auth(f):
    """
    Decorator to require API key authentication.
    
    Checks for X-API-Key header against configured API key.
    If auth is not enabled (no API_KEY set), all requests pass through.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not config.auth.enabled:
            return f(*args, **kwargs)
        
        api_key = request.headers.get('X-API-Key', '')
        if not api_key or api_key != config.auth.api_key:
            logger.warning(
                f"Unauthorized request to {request.method} {request.path} "
                f"from {request.remote_addr}"
            )
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Valid API key required. Set X-API-Key header.'
            }), 401
        
        return f(*args, **kwargs)
    return decorated


def protect_blueprint(bp):
    """
    Register before_request hook on a blueprint to protect mutating methods.
    
    GET and OPTIONS pass through; POST/PUT/PATCH/DELETE require auth.
    """
    @bp.before_request
    def check_auth():
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None  # Allow read-only requests
        
        if not config.auth.enabled:
            return None
        
        api_key = request.headers.get('X-API-Key', '')
        if not api_key or api_key != config.auth.api_key:
            logger.warning(
                f"Unauthorized {request.method} {request.path} "
                f"from {request.remote_addr}"
            )
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Valid API key required. Set X-API-Key header.'
            }), 401


# Apply auth protection to all blueprints
for _bp in [playlists_bp, channels_bp, vod_bp, groups_bp, epg_bp, series_bp, sources_bp]:
    protect_blueprint(_bp)