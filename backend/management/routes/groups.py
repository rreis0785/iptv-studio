"""
Group (Category) API routes.
"""

from flask import Blueprint, jsonify, request

from management.services import services

bp = Blueprint('groups', __name__, url_prefix='/api/groups')


@bp.route('', methods=['GET'])
def list_groups():
    """List all groups."""
    playlist_id = request.args.get('playlist_id')
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    
    groups = services.groups.get_all(
        playlist_id=playlist_id,
        include_hidden=include_hidden
    )
    
    return jsonify({
        'count': len(groups),
        'groups': [g.to_dict() for g in groups]
    })


@bp.route('', methods=['POST'])
def create_group():
    """Create a new group."""
    data = request.get_json() or {}
    
    required = ['name', 'playlist_id']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    try:
        group = services.groups.create(**data)
        return jsonify(group.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except (TypeError, KeyError) as e:
        return jsonify({'error': f'Invalid data: {e}'}), 400


@bp.route('/bulk', methods=['POST'])
def bulk_create_groups():
    """Create multiple groups."""
    data = request.get_json() or {}
    playlist_id = data.get('playlist_id')
    groups_data = data.get('groups', [])
    
    if not playlist_id:
        return jsonify({'error': 'playlist_id is required'}), 400
    if not groups_data or not isinstance(groups_data, list):
        return jsonify({'error': 'groups array is required'}), 400
    
    try:
        created, errors = services.groups.bulk_create(groups_data, playlist_id)
        return jsonify({
            'success': True,
            'created': len(created),
            'errors': len(errors),
            'groups': [g.to_dict() for g in created],
            'error_details': errors
        }), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<group_id>', methods=['GET'])
def get_group(group_id: str):
    """Get group by ID with counts."""
    group = services.groups.get(group_id, include_counts=True)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    return jsonify(group.to_dict())


@bp.route('/<group_id>', methods=['PUT', 'PATCH'])
def update_group(group_id: str):
    """Update a group."""
    data = request.get_json() or {}
    
    group = services.groups.update(group_id, data)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    return jsonify(group.to_dict())


@bp.route('/<group_id>', methods=['DELETE'])
def delete_group(group_id: str):
    """Delete a group."""
    move_to = request.args.get('move_to')  # Group ID to move contents to
    
    if services.groups.delete(group_id, move_to_group=move_to):
        return jsonify({'success': True, 'message': 'Group deleted'})
    return jsonify({'error': 'Group not found'}), 404


@bp.route('/reorder', methods=['POST'])
def reorder_groups():
    """Reorder groups."""
    data = request.get_json() or {}
    group_ids = data.get('group_ids', [])
    
    if not group_ids:
        return jsonify({'error': 'group_ids is required'}), 400
    
    updated = services.groups.reorder(group_ids)
    
    return jsonify({
        'success': True,
        'updated': updated
    })


@bp.route('/merge', methods=['POST'])
def merge_groups():
    """Merge source group into target group."""
    data = request.get_json() or {}
    source_id = data.get('source_id')
    target_id = data.get('target_id')
    
    if not source_id or not target_id:
        return jsonify({'error': 'source_id and target_id are required'}), 400
    
    if services.groups.merge(source_id, target_id):
        return jsonify({'success': True, 'message': 'Groups merged'})
    return jsonify({'error': 'One or both groups not found'}), 404


# Group contents

@bp.route('/<group_id>/channels', methods=['GET'])
def get_group_channels(group_id: str):
    """Get channels in a group."""
    group = services.groups.get(group_id)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    
    channels = services.channels.get_all(
        playlist_id=group.playlist_id,
        group_id=group_id,
        include_hidden=include_hidden
    )
    
    return jsonify({
        'count': len(channels),
        'channels': [c.to_dict() for c in channels]
    })


@bp.route('/<group_id>/vod', methods=['GET'])
def get_group_vod(group_id: str):
    """Get VOD in a group."""
    group = services.groups.get(group_id)
    if not group:
        return jsonify({'error': 'Group not found'}), 404
    
    include_hidden = request.args.get('include_hidden', 'false').lower() == 'true'
    content_type = request.args.get('content_type')
    
    vods = services.vod.get_all(
        playlist_id=group.playlist_id,
        group_id=group_id,
        content_type=content_type,
        include_hidden=include_hidden
    )
    
    return jsonify({
        'count': len(vods),
        'vod': [v.to_dict() for v in vods]
    })