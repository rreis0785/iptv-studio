"""
EPG (Electronic Program Guide) API routes.
"""

from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request

from management.services import services

bp = Blueprint('epg', __name__, url_prefix='/api/epg')


@bp.route('', methods=['GET'])
def list_programs():
    """List EPG programs with filtering."""
    channel_id = request.args.get('channel_id')
    
    if not channel_id:
        return jsonify({'error': 'channel_id is required'}), 400
    
    # Parse time filters
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
    
    limit = min(int(request.args.get('limit', 100)), 500)
    
    programs = services.epg.get_by_channel(
        channel_id,
        start_time=start_time,
        end_time=end_time,
        limit=limit
    )
    
    return jsonify({
        'count': len(programs),
        'programs': [p.to_dict() for p in programs]
    })


@bp.route('', methods=['POST'])
def create_program():
    """Create a new EPG program."""
    data = request.get_json() or {}
    
    required = ['channel_id', 'title', 'start_time', 'end_time']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    # Parse datetime strings
    try:
        if isinstance(data['start_time'], str):
            data['start_time'] = datetime.fromisoformat(
                data['start_time'].replace('Z', '+00:00')
            )
        if isinstance(data['end_time'], str):
            data['end_time'] = datetime.fromisoformat(
                data['end_time'].replace('Z', '+00:00')
            )
    except ValueError:
        return jsonify({'error': 'Invalid datetime format'}), 400
    
    try:
        program = services.epg.create(**data)
        return jsonify(program.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/bulk', methods=['POST'])
def bulk_create_programs():
    """Create multiple EPG programs."""
    data = request.get_json() or {}
    programs = data.get('programs', [])
    
    if not programs:
        return jsonify({'error': 'programs array is required'}), 400
    
    # Parse datetime strings in all programs
    for prog in programs:
        try:
            if isinstance(prog.get('start_time'), str):
                prog['start_time'] = datetime.fromisoformat(
                    prog['start_time'].replace('Z', '+00:00')
                )
            if isinstance(prog.get('end_time'), str):
                prog['end_time'] = datetime.fromisoformat(
                    prog['end_time'].replace('Z', '+00:00')
                )
        except ValueError:
            continue  # Skip invalid entries
    
    created = services.epg.bulk_create(programs)
    
    return jsonify({
        'success': True,
        'created': len(created),
        'programs': [p.to_dict() for p in created]
    }), 201


@bp.route('/<program_id>', methods=['GET'])
def get_program(program_id: str):
    """Get EPG program by ID."""
    program = services.epg.get(program_id)
    if not program:
        return jsonify({'error': 'Program not found'}), 404
    
    return jsonify(program.to_dict())


@bp.route('/<program_id>', methods=['PUT', 'PATCH'])
def update_program(program_id: str):
    """Update an EPG program."""
    data = request.get_json() or {}
    
    # Parse datetime strings
    try:
        if isinstance(data.get('start_time'), str):
            data['start_time'] = datetime.fromisoformat(
                data['start_time'].replace('Z', '+00:00')
            )
        if isinstance(data.get('end_time'), str):
            data['end_time'] = datetime.fromisoformat(
                data['end_time'].replace('Z', '+00:00')
            )
    except ValueError:
        return jsonify({'error': 'Invalid datetime format'}), 400
    
    program = services.epg.update(program_id, data)
    if not program:
        return jsonify({'error': 'Program not found'}), 404
    
    return jsonify(program.to_dict())


@bp.route('/<program_id>', methods=['DELETE'])
def delete_program(program_id: str):
    """Delete an EPG program."""
    if services.epg.delete(program_id):
        return jsonify({'success': True, 'message': 'Program deleted'})
    return jsonify({'error': 'Program not found'}), 404


@bp.route('/current', methods=['GET'])
def get_current_programs():
    """Get currently airing programs for channels."""
    channel_ids = request.args.getlist('channel_id')
    
    if not channel_ids:
        return jsonify({'error': 'At least one channel_id is required'}), 400
    
    result = {}
    for channel_id in channel_ids:
        program = services.epg.get_current(channel_id)
        result[channel_id] = program.to_dict() if program else None
    
    return jsonify(result)


@bp.route('/schedule/<channel_id>', methods=['GET'])
def get_schedule(channel_id: str):
    """Get full day schedule for a channel."""
    channel = services.channels.get(channel_id)
    if not channel:
        return jsonify({'error': 'Channel not found'}), 404
    
    date = None
    if date_str := request.args.get('date'):
        try:
            date = datetime.fromisoformat(date_str)
        except ValueError:
            return jsonify({'error': 'Invalid date format'}), 400
    
    programs = services.epg.get_schedule(channel_id, date)
    
    return jsonify({
        'channel_id': channel_id,
        'channel_name': channel.name,
        'date': (date or datetime.now(timezone.utc)).date().isoformat(),
        'count': len(programs),
        'programs': [p.to_dict() for p in programs]
    })


@bp.route('/channel/<channel_id>/clear', methods=['DELETE'])
def clear_channel_epg(channel_id: str):
    """Clear all EPG data for a channel."""
    deleted = services.epg.clear_channel(channel_id)
    
    return jsonify({
        'success': True,
        'deleted': deleted
    })


@bp.route('/cleanup', methods=['POST'])
def cleanup_old_epg():
    """Clear old EPG data."""
    data = request.get_json() or {}
    
    before = None
    if before_str := data.get('before'):
        try:
            before = datetime.fromisoformat(before_str.replace('Z', '+00:00'))
        except ValueError:
            return jsonify({'error': 'Invalid datetime format'}), 400
    
    deleted = services.epg.clear_old(before)
    
    return jsonify({
        'success': True,
        'deleted': deleted
    })