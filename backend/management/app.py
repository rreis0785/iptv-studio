"""
Flask application factory.
"""

import logging
import time

from flask import Flask, jsonify
from flask_cors import CORS

from management.config import config
from management.storage import storage


def create_app(test_config: dict = None) -> Flask:
    """
    Application factory for creating Flask app instances.
    
    Args:
        test_config: Optional configuration overrides for testing
        
    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    
    # Apply configuration
    app.config.update(
        DEBUG=config.server.debug,
        TESTING=False,
    )
    
    if test_config:
        app.config.update(test_config)
    
    # Configure CORS
    CORS(app, resources={
        r"/api/*": {
            "origins": config.server.cors_origins,
            "methods": config.server.cors_methods,
            "allow_headers": config.server.cors_headers,
        }
    })
    
    # Configure logging
    logging.basicConfig(
        level=config.log.level,
        format=config.log.format,
    )
    
    # Register blueprints
    register_blueprints(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register health endpoint
    register_health_endpoint(app)
    
    return app


def register_blueprints(app: Flask) -> None:
    """Register all API blueprints."""
    from management.routes import (
        playlists_bp,
        channels_bp,
        vod_bp,
        groups_bp,
        epg_bp,
        series_bp,
        sources_bp,
    )
    
    app.register_blueprint(playlists_bp)
    app.register_blueprint(channels_bp)
    app.register_blueprint(vod_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(epg_bp)
    app.register_blueprint(series_bp)
    app.register_blueprint(sources_bp)


def register_error_handlers(app: Flask) -> None:
    """Register global error handlers."""
    
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': 'Bad request'}), 400
    
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({'error': 'Method not allowed'}), 405
    
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Internal server error")
        return jsonify({'error': 'Internal server error'}), 500


def register_health_endpoint(app: Flask) -> None:
    """Register health check endpoint."""
    
    @app.route('/api/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        stats = storage.get_stats()
        
        return jsonify({
            'status': 'ok',
            'timestamp': time.time(),
            'version': '1.0.0',
            'storage': {
                'backend': config.storage.backend,
                'stats': stats
            }
        })
    
    @app.route('/api/stats', methods=['GET'])
    def stats():
        """Get storage statistics."""
        return jsonify(storage.get_stats())
    
    @app.route('/api/reset', methods=['POST'])
    def reset():
        """Reset all data (development only)."""
        if not app.debug:
            return jsonify({'error': 'Only available in debug mode'}), 403
        
        cleared = storage.clear_all()
        return jsonify({
            'success': True,
            'cleared': cleared
        })