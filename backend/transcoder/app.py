"""
Flask application factory.

This module provides the ``create_app()`` function for creating configured
Flask application instances.

Test usage
----------
When running under pytest, pass ``start_cleanup=False`` to prevent the
background cleanup thread from leaking across test cases::

    app = create_app(test_config={"TESTING": True}, start_cleanup=False)
"""

import logging

from flask import Flask, jsonify
from flask_cors import CORS

from transcoder.config import config
from transcoder.manager import manager
from transcoder.routes import api

logger = logging.getLogger(__name__)


def create_app(
    test_config: dict = None,
    *,
    start_cleanup: bool = True,
) -> Flask:
    """
    Application factory for creating Flask app instances.

    Args:
        test_config:    Optional Flask config overrides (applied after
                        defaults, so ``TESTING=True`` works as expected).
        start_cleanup:  When ``True`` (the default) the stream-manager
                        background cleanup thread is started.  Pass
                        ``False`` in test contexts to avoid thread leaks.

    Returns:
        Configured Flask application.

    Example::

        from transcoder import create_app

        app = create_app()
        app.run(host='0.0.0.0', port=5000)
    """
    # Configure root logging once, before the app is constructed so that any
    # import-time log calls are captured with the right level and format.
    logging.basicConfig(
        level=config.log.level,
        format=config.log.format,
    )

    app = Flask(__name__)

    # Base Flask config
    app.config.update(
        DEBUG=config.server.debug,
        TESTING=False,
    )

    # Test overrides applied after defaults so callers can set TESTING=True,
    # override DEBUG, inject fake config values, etc.
    if test_config:
        app.config.update(test_config)

    # CORS — restrict to /api/* only
    CORS(app, resources={
        r"/api/*": {
            "origins": config.server.cors_origins,
            "methods": config.server.cors_methods,
            "allow_headers": config.server.cors_headers,
        }
    })

    # Blueprints
    app.register_blueprint(api)

    # Error handlers
    _register_error_handlers(app)

    # Background cleanup thread — skipped in test contexts to prevent leaks
    if start_cleanup:
        manager.start_cleanup_thread()
        logger.debug("Stream manager cleanup thread started")

    return app


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

def _register_error_handlers(app: Flask) -> None:
    """Register JSON error handlers for common HTTP error codes."""

    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            'error': 'Bad request',
            'message': str(error.description) if error.description else 'Invalid request',
        }), 400

    @app.errorhandler(401)
    def unauthorized(error):
        return jsonify({
            'error': 'Unauthorized',
            'message': 'Valid authentication credentials are required',
        }), 401

    @app.errorhandler(403)
    def forbidden(error):
        return jsonify({
            'error': 'Forbidden',
            'message': 'You do not have permission to access this resource',
        }), 403

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'error': 'Not found',
            'message': 'The requested resource does not exist',
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            'error': 'Method not allowed',
            'message': f'Allowed methods: {", ".join(error.valid_methods or [])}',
        }), 405

    @app.errorhandler(429)
    def too_many_requests(error):
        return jsonify({
            'error': 'Too many requests',
            'message': 'Rate limit exceeded. Please slow down.',
        }), 429

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception("Unhandled internal server error")
        return jsonify({
            'error': 'Internal server error',
            'message': 'An unexpected error occurred',
        }), 500