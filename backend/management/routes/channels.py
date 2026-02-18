"""
Channel API routes (Live Streams).
"""

from flask import Blueprint, jsonify, request

from management.services import services
from management.validators import validate_channel_data, validate_url, strip_readonly_fields
from management.limiter import limiter

bp = Blueprint('channels', __name__, url_prefix='/api/channels')


@bp.route('', methods=['GET'])
def list_channels():
    """List all channels."""
    playlist_id = request.args.get('playlist_id')
    group_id = request.args.get('group_id')
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    
    channels = services.channels.get_all(
        playlist_id=playlist_id,
        group_id=group_id,
        include_hidden=include_hidden
    )
    
    return jsonify({
        'count': len(channels),
        'channels': [c.to_dict() for c in channels]
    })


@bp.route('', methods=['POST'])
def create_channel():
    """Create a new channel."""
    data = strip_readonly_fields(request.get_json() or {})

    required = ['name', 'url', 'playlist_id']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Validate URL
    url_error = validate_url(data['url'])
    if url_error:
        return jsonify({'error': url_error}), 400
    
    try:
        channel = services.channels.create(**data)
        return jsonify(channel.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except (TypeError, KeyError) as e:
        return jsonify({'error': f'Invalid data: {e}'}), 400


@bp.route('/bulk', methods=['POST'])
@limiter.limit("10 per minute")
def bulk_create_channels():
    """Create multiple channels."""
    data = request.get_json() or {}
    playlist_id = data.get('playlist_id')
    channels_data = data.get('channels', [])
    
    if not playlist_id:
        return jsonify({'error': 'playlist_id is required'}), 400
    if not channels_data or not isinstance(channels_data, list):
        return jsonify({'error': 'channels array is required'}), 400
    
    try:
        created, errors = services.channels.bulk_create(channels_data, playlist_id)
        return jsonify({
            'success': True,
            'created': len(created),
            'errors': len(errors),
            'channels': [c.to_dict() for c in created],
            'error_details': errors
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/bulk-update', methods=['POST'])
def bulk_update_channels():
    """Update multiple channels."""
    data = request.get_json() or {}
    updates = data.get('channels', [])
    
    if not updates or not isinstance(updates, list):
        return jsonify({'error': 'channels array is required'}), 400
    
    updated, errors = services.channels.bulk_update(updates)
    
    return jsonify({
        'success': True,
        'updated': len(updated),
        'errors': len(errors),
        'channels': [c.to_dict() for c in updated],
        'error_details': errors
    })


@bp.route('/<channel_id>', methods=['GET'])
def get_channel(channel_id: str):
    """Get channel by ID."""
    include_epg = request.args.get('include_epg', 'false').lower() == 'true'
    
    channel = services.channels.get(channel_id, include_epg=include_epg)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    return jsonify(channel.to_dict())


@bp.route('/<channel_id>', methods=['PUT', 'PATCH'])
def update_channel(channel_id: str):
    """Update a channel."""
    data = strip_readonly_fields(request.get_json() or {})

    if 'url' in data and data['url']:
        url_error = validate_url(data['url'])
        if url_error:
            return jsonify({'error': url_error}), 400

    try:
        channel = services.channels.update(channel_id, data)
        if not channel:
            return jsonify({'error': 'Channel not found'}), 404
        return jsonify(channel.to_dict())
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<channel_id>', methods=['DELETE'])
def delete_channel(channel_id: str):
    """Delete a channel."""
    if services.channels.delete(channel_id):
        return jsonify({'success': True, 'message': 'Channel deleted'})
    return jsonify({'error': 'Channel not found'}), 404


@bp.route('/search', methods=['GET'])
def search_channels():
    """Search channels by name."""
    query = request.args.get('q', '')
    playlist_id = request.args.get('playlist_id')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400
    
    channels = services.channels.search(query, playlist_id, limit)
    
    return jsonify({
        'count': len(channels),
        'channels': [c.to_dict() for c in channels]
    })


@bp.route('/favorites', methods=['GET'])
def get_favorites():
    """Get favorite channels."""
    playlist_id = request.args.get('playlist_id')
    channels = services.channels.get_favorites(playlist_id)
    
    return jsonify({
        'count': len(channels),
        'channels': [c.to_dict() for c in channels]
    })


@bp.route('/<channel_id>/favorite', methods=['POST', 'DELETE'])
def toggle_favorite(channel_id: str):
    """Toggle channel favorite status."""
    channel = services.channels.toggle_favorite(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    return jsonify({
        'success': True,
        'is_favorite': channel.is_favorite
    })


@bp.route('/reorder', methods=['POST'])
def reorder_channels():
    """Reorder channels."""
    data = request.get_json() or {}
    channel_ids = data.get('channel_ids', [])
    
    if not channel_ids:
        return jsonify({'error': 'channel_ids is required'}), 400
    
    updated = services.channels.reorder(channel_ids)
    
    return jsonify({
        'success': True,
        'updated': updated
    })


@bp.route('/move', methods=['POST'])
def move_channels():
    """Move channels to a group."""
    data = request.get_json() or {}
    channel_ids = data.get('channel_ids', [])
    group_id = data.get('group_id')  # None = ungroup
    
    if not channel_ids:
        return jsonify({'error': 'channel_ids is required'}), 400
    
    try:
        updated = services.channels.move_to_group(channel_ids, group_id)
        return jsonify({
            'success': True,
            'updated': updated
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/bulk-delete', methods=['POST'])
def bulk_delete_channels():
    """Delete multiple channels."""
    data = request.get_json() or {}
    channel_ids = data.get('channel_ids', [])
    
    if not channel_ids:
        return jsonify({'error': 'channel_ids is required'}), 400
    
    deleted = services.channels.bulk_delete(channel_ids)
    
    return jsonify({
        'success': True,
        'deleted': deleted
    })


# EPG for channel

@bp.route('/<channel_id>/epg', methods=['GET'])
def get_channel_epg(channel_id: str):
    """Get EPG for a channel."""
    from datetime import datetime
    
    channel = services.channels.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    # Parse date parameters
    start_time = None
    end_time = None
    
    if start := request.args.get('start'):
        try:
            start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': 'Invalid start time format'}), 400
    
    if end := request.args.get('end'):
        try:
            end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': 'Invalid end time format'}), 400
    
    programs = services.epg.get_by_channel(
        channel_id,
        start_time=start_time,
        end_time=end_time
    )
    
    current = services.epg.get_current(channel_id)
    
    return jsonify({
        'count': len(programs),
        'current': current.to_dict() if current else None,
        'programs': [p.to_dict() for p in programs]
    })


@bp.route('/<channel_id>/epg/current', methods=['GET'])
def get_current_program(channel_id: str):
    """Get currently airing program."""
    channel = services.channels.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    program = services.epg.get_current(channel_id)
    if not program:
        return jsonify({'message': 'No current program'}), 404
    
    return jsonify(program.to_dict())


# Sources for channel

@bp.route('/<channel_id>/sources', methods=['GET'])
def get_channel_sources(channel_id: str):
    """Get stream sources for a channel."""
    channel = services.channels.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    sources = services.sources.get_by_channel(channel_id)
    
    return jsonify({
        'count': len(sources),
        'sources': [s.to_dict() for s in sources]
    })


@bp.route('/<channel_id>/sources', methods=['POST'])
def add_channel_source(channel_id: str):
    """Add a stream source to a channel."""
    channel = services.channels.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    data = request.get_json() or {}
    if not data.get('url'):
        return jsonify({'error': 'url is required'}), 400
    
    data['channel_id'] = channel_id
    
    try:
        source = services.sources.create(**data)
        return jsonify(source.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400