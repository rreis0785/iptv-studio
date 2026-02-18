"""
Stream Source API routes.
"""

from flask import Blueprint, jsonify, request

from management.services import services

bp = Blueprint('sources', __name__, url_prefix='/api/sources')


@bp.route('', methods=['GET'])
def list_sources():
    """List sources for a channel/VOD."""
    channel_id = request.args.get('channel_id')
    
    if not channel_id:
        return jsonify({'error': 'channel_id is required'}), 400
    
    sources = services.sources.get_by_channel(channel_id)
    
    return jsonify({
        'count': len(sources),
        'sources': [s.to_dict() for s in sources]
    })


@bp.route('', methods=['POST'])
def create_source():
    """Create a new stream source."""
    data = request.get_json() or {}
    
    required = ['channel_id', 'url']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    try:
        source = services.sources.create(**data)
        return jsonify(source.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<source_id>', methods=['GET'])
def get_source(source_id: str):
    """Get source by ID."""
    source = services.sources.get(source_id)
    if not source:
        return jsonify({'error': 'Source not found'}), 404
    
    return jsonify(source.to_dict())


@bp.route('/<source_id>', methods=['PUT', 'PATCH'])
def update_source(source_id: str):
    """Update a source."""
    data = request.get_json() or {}
    
    source = services.sources.update(source_id, data)
    if not source:
        return jsonify({'error': 'Source not found'}), 404
    
    return jsonify(source.to_dict())


@bp.route('/<source_id>', methods=['DELETE'])
def delete_source(source_id: str):
    """Delete a source."""
    if services.sources.delete(source_id):
        return jsonify({'success': True, 'message': 'Source deleted'})
    return jsonify({'error': 'Source not found'}), 404


@bp.route('/<source_id>/primary', methods=['POST'])
def set_primary(source_id: str):
    """Set source as primary."""
    if services.sources.set_primary(source_id):
        return jsonify({'success': True, 'message': 'Source set as primary'})
    return jsonify({'error': 'Source not found'}), 404