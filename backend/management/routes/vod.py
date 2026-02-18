"""
VOD (Video on Demand) API routes.
"""

from flask import Blueprint, jsonify, request

from management.services import services
from management.validators import validate_url

bp = Blueprint('vod', __name__, url_prefix='/api/vod')


@bp.route('', methods=['GET'])
def list_vod():
    """List all VOD items."""
    playlist_id = request.args.get('playlist_id')
    group_id = request.args.get('group_id')
    content_type = request.args.get('content_type')
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    
    vods = services.vod.get_all(
        playlist_id=playlist_id,
        group_id=group_id,
        content_type=content_type,
        include_hidden=include_hidden
    )
    
    return jsonify({
        'count': len(vods),
        'vod': [v.to_dict() for v in vods]
    })


@bp.route('', methods=['POST'])
def create_vod():
    """Create a new VOD item."""
    data = request.get_json() or {}
    
    required = ['name', 'url', 'playlist_id']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate URL
    url_error = validate_url(data['url'])
    if url_error:
        return jsonify({'error': url_error}), 400
    
    try:
        vod = services.vod.create(**data)
        return jsonify(vod.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except (TypeError, KeyError) as e:
        return jsonify({'error': f'Invalid data: {e}'}), 400


@bp.route('/bulk', methods=['POST'])
def bulk_create_vod():
    """Create multiple VOD items."""
    data = request.get_json() or {}
    playlist_id = data.get('playlist_id')
    vods_data = data.get('vod', [])
    
    if not playlist_id:
        return jsonify({'error': 'playlist_id is required'}), 400
    if not vods_data or not isinstance(vods_data, list):
        return jsonify({'error': 'vod array is required'}), 400
    
    try:
        created, errors = services.vod.bulk_create(vods_data, playlist_id)
        return jsonify({
            'success': True,
            'created': len(created),
            'errors': len(errors),
            'vod': [v.to_dict() for v in created],
            'error_details': errors
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/bulk-update', methods=['POST'])
def bulk_update_vod():
    """Update multiple VOD items."""
    data = request.get_json() or {}
    updates = data.get('vod', [])
    
    if not updates or not isinstance(updates, list):
        return jsonify({'error': 'vod array is required'}), 400
    
    updated, errors = services.vod.bulk_update(updates)
    
    return jsonify({
        'success': True,
        'updated': len(updated),
        'errors': len(errors),
        'vod': [v.to_dict() for v in updated],
        'error_details': errors
    })


@bp.route('/<vod_id>', methods=['GET'])
def get_vod(vod_id: str):
    """Get VOD by ID."""
    vod = services.vod.get(vod_id)
    if not vod:
        return jsonify({'error': 'VOD not found'}), 404
    
    return jsonify(vod.to_dict())


@bp.route('/<vod_id>', methods=['PUT', 'PATCH'])
def update_vod(vod_id: str):
    """Update a VOD item."""
    data = request.get_json() or {}
    
    try:
        vod = services.vod.update(vod_id, data)
        if not vod:
            return jsonify({'error': 'VOD not found'}), 404
        return jsonify(vod.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<vod_id>', methods=['DELETE'])
def delete_vod(vod_id: str):
    """Delete a VOD item."""
    if services.vod.delete(vod_id):
        return jsonify({'success': True, 'message': 'VOD deleted'})
    return jsonify({'error': 'VOD not found'}), 404


@bp.route('/search', methods=['GET'])
def search_vod():
    """Search VOD by name or plot."""
    query = request.args.get('q', '')
    playlist_id = request.args.get('playlist_id')
    content_type = request.args.get('content_type')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400
    
    vods = services.vod.search(query, playlist_id, content_type, limit)
    
    return jsonify({
        'count': len(vods),
        'vod': [v.to_dict() for v in vods]
    })


@bp.route('/continue-watching', methods=['GET'])
def continue_watching():
    """Get in-progress VOD items."""
    playlist_id = request.args.get('playlist_id')
    limit = min(int(request.args.get('limit', 20)), 50)
    
    vods = services.vod.get_continue_watching(playlist_id, limit)
    
    return jsonify({
        'count': len(vods),
        'vod': [v.to_dict() for v in vods]
    })


@bp.route('/recently-watched', methods=['GET'])
def recently_watched():
    """Get recently watched VOD items."""
    playlist_id = request.args.get('playlist_id')
    limit = min(int(request.args.get('limit', 20)), 50)
    
    vods = services.vod.get_recently_watched(playlist_id, limit)
    
    return jsonify({
        'count': len(vods),
        'vod': [v.to_dict() for v in vods]
    })


@bp.route('/<vod_id>/progress', methods=['POST', 'PUT'])
def update_progress(vod_id: str):
    """Update watch progress."""
    data = request.get_json() or {}
    
    position = data.get('position')
    if position is None:
        return jsonify({'error': 'position is required'}), 400
    
    completed = data.get('completed')
    
    vod = services.vod.update_watch_progress(vod_id, position, completed)
    if not vod:
        return jsonify({'error': 'VOD not found'}), 404
    
    return jsonify({
        'success': True,
        'watch_position': vod.watch_position,
        'watch_completed': vod.watch_completed,
        'watch_progress_percent': vod.watch_progress_percent
    })


@bp.route('/<vod_id>/progress', methods=['DELETE'])
def reset_progress(vod_id: str):
    """Reset watch progress."""
    vod = services.vod.update_watch_progress(vod_id, 0, False)
    if not vod:
        return jsonify({'error': 'VOD not found'}), 404
    
    return jsonify({'success': True, 'message': 'Progress reset'})


@bp.route('/<vod_id>/favorite', methods=['POST', 'DELETE'])
def toggle_favorite(vod_id: str):
    """Toggle VOD favorite status."""
    vod = services.vod.toggle_favorite(vod_id)
    if not vod:
        return jsonify({'error': 'VOD not found'}), 404
    
    return jsonify({
        'success': True,
        'is_favorite': vod.is_favorite
    })


@bp.route('/bulk-delete', methods=['POST'])
def bulk_delete_vod():
    """Delete multiple VOD items."""
    data = request.get_json() or {}
    vod_ids = data.get('vod_ids', [])
    
    if not vod_ids:
        return jsonify({'error': 'vod_ids is required'}), 400
    
    deleted = services.vod.bulk_delete(vod_ids)
    
    return jsonify({
        'success': True,
        'deleted': deleted
    })


# Sources for VOD

@bp.route('/<vod_id>/sources', methods=['GET'])
def get_vod_sources(vod_id: str):
    """Get stream sources for a VOD item."""
    vod = services.vod.get(vod_id)
    if not vod:
        return jsonify({'error': 'VOD not found'}), 404
    
    sources = services.sources.get_by_channel(vod_id)
    
    return jsonify({
        'count': len(sources),
        'sources': [s.to_dict() for s in sources]
    })


@bp.route('/<vod_id>/sources', methods=['POST'])
def add_vod_source(vod_id: str):
    """Add a stream source to a VOD item."""
    vod = services.vod.get(vod_id)
    if not vod:
        return jsonify({'error': 'VOD not found'}), 404
    
    data = request.get_json() or {}
    if not data.get('url'):
        return jsonify({'error': 'url is required'}), 400
    
    data['channel_id'] = vod_id
    
    try:
        source = services.sources.create(**data)
        return jsonify(source.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400