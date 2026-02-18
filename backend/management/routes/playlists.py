"""
Playlist API routes.
"""

from flask import Blueprint, jsonify, request

from management.services import services
from management.validators import strip_readonly_fields
from management.limiter import limiter

bp = Blueprint('playlists', __name__, url_prefix='/api/playlists')


@bp.route('', methods=['GET'])
def list_playlists():
    """List all playlists."""
    playlists = services.playlists.get_all()
    return jsonify({
        'count': len(playlists),
        'playlists': [p.to_dict() for p in playlists]
    })


@bp.route('', methods=['POST'])
def create_playlist():
    """Create a new playlist."""
    data = strip_readonly_fields(request.get_json() or {})

    if not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400

    try:
        playlist = services.playlists.create(**data)
        return jsonify(playlist.to_dict()), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<playlist_id>', methods=['GET'])
def get_playlist(playlist_id: str):
    """Get playlist by ID with stats."""
    data = services.playlists.get_with_stats(playlist_id)
    if not data:
        return jsonify({'error': 'Playlist not found'}), 404
    return jsonify(data)


@bp.route('/<playlist_id>', methods=['PUT', 'PATCH'])
def update_playlist(playlist_id: str):
    """Update a playlist."""
    data = strip_readonly_fields(request.get_json() or {})

    playlist = services.playlists.update(playlist_id, data)
    if not playlist:
        return jsonify({'error': 'Playlist not found'}), 404
    
    return jsonify(playlist.to_dict())


@bp.route('/<playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id: str):
    """Delete a playlist."""
    cascade = request.args.get('cascade', 'true').lower() == 'true'
    
    if services.playlists.delete(playlist_id, cascade=cascade):
        return jsonify({'success': True, 'message': 'Playlist deleted'})
    return jsonify({'error': 'Playlist not found'}), 404


@bp.route('/<playlist_id>/default', methods=['POST'])
def set_default_playlist(playlist_id: str):
    """Set playlist as default."""
    if services.playlists.set_default(playlist_id):
        return jsonify({'success': True, 'message': 'Playlist set as default'})
    return jsonify({'error': 'Playlist not found'}), 404


@bp.route('/import', methods=['POST'])
@limiter.limit("10 per minute")
def import_playlist():
    """
    Import playlist from file or content.
    
    Supports:
    - Multipart file upload ('file')
    - Raw body content
    - Form/Query params: format (m3u/json/xml), name
    """
    content = None
    name = request.values.get('name')
    fmt = request.values.get('format')
    
    # Handle file upload
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            content = file.read().decode('utf-8', errors='replace')
            if not name:
                name = file.filename.rsplit('.', 1)[0]
    # Handle raw content
    elif request.data:
        content = request.get_data(as_text=True)
    
    if not content:
        return jsonify({'error': 'No content provided'}), 400
    
    try:
        result = services.playlists.import_playlist(
            content=content,
            format=fmt,
            name=name
        )
        return jsonify({
            'success': True,
            'playlist': result['playlist'].to_dict(),
            'stats': {
                'channels': result['channels'],
                'vod': result['vod'],
                'groups': result['groups']
            }
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@bp.route('/<playlist_id>/export', methods=['GET'])
def export_playlist(playlist_id: str):
    """
    Export playlist.
    
    Params:
        format: m3u (default), json, xml
        include_vod: true/false
    """
    include_vod = request.args.get('include_vod', 'false').lower() == 'true'
    fmt = request.args.get('format', 'm3u').lower()
    
    try:
        content = services.playlists.export_playlist(
            playlist_id,
            format=fmt,
            include_vod=include_vod
        )
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
        
    if content is None:
        return jsonify({'error': 'Playlist not found'}), 404
    
    # Set headers based on format
    content_type = 'text/plain'
    extension = 'txt'
    
    if fmt in ('m3u', 'm3u8'):
        content_type = 'audio/x-mpegurl'
        extension = 'm3u'
    elif fmt == 'json':
        content_type = 'application/json'
        extension = 'json'
    elif fmt == 'xml':
        content_type = 'application/xml'
        extension = 'xml'
    
    return content, 200, {
        'Content-Type': content_type,
        'Content-Disposition': f'attachment; filename=playlist_{playlist_id}.{extension}'
    }


# Nested routes for playlist contents

@bp.route('/<playlist_id>/channels', methods=['GET'])
def list_playlist_channels(playlist_id: str):
    """List channels in a playlist."""
    if not services.playlists.get(playlist_id):
        return jsonify({'error': 'Playlist not found'}), 404
    
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


@bp.route('/<playlist_id>/vod', methods=['GET'])
def list_playlist_vod(playlist_id: str):
    """List VOD in a playlist."""
    if not services.playlists.get(playlist_id):
        return jsonify({'error': 'Playlist not found'}), 404
    
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


@bp.route('/<playlist_id>/groups', methods=['GET'])
def list_playlist_groups(playlist_id: str):
    """List groups in a playlist."""
    if not services.playlists.get(playlist_id):
        return jsonify({'error': 'Playlist not found'}), 404
    
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    
    groups = services.groups.get_all(
        playlist_id=playlist_id,
        include_hidden=include_hidden
    )
    
    return jsonify({
        'count': len(groups),
        'groups': [g.to_dict() for g in groups]
    })


@bp.route('/<playlist_id>/series', methods=['GET'])
def list_playlist_series(playlist_id: str):
    """List series in a playlist."""
    if not services.playlists.get(playlist_id):
        return jsonify({'error': 'Playlist not found'}), 404
    
    series_list = services.series.get_all(playlist_id=playlist_id)
    
    return jsonify({
        'count': len(series_list),
        'series': [s.to_dict() for s in series_list]
    })