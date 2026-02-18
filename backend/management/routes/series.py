"""
Series API routes.
"""

from flask import Blueprint, jsonify, request

from management.services import services

bp = Blueprint('series', __name__, url_prefix='/api/series')


@bp.route('', methods=['GET'])
def list_series():
    """List all series."""
    playlist_id = request.args.get('playlist_id')
    
    series_list = services.series.get_all(playlist_id=playlist_id)
    
    return jsonify({
        'count': len(series_list),
        'series': [s.to_dict() for s in series_list]
    })


@bp.route('', methods=['POST'])
def create_series():
    """Create a new series."""
    data = request.get_json() or {}
    
    required = ['name', 'playlist_id']
    for field in required:
        if not data.get(field):
            return jsonify({'error': f'{field} is required'}), 400
    
    try:
        series = services.series.create(**data)
        return jsonify(series.to_dict()), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.route('/<series_id>', methods=['GET'])
def get_series(series_id: str):
    """Get series by ID."""
    include_episodes = request.args.get('include_episodes', 'false').lower() == 'true'
    
    series = services.series.get(series_id, include_episodes=include_episodes)
    if not series:
        return jsonify({'error': 'Series not found'}), 404
    
    return jsonify(series.to_dict())


@bp.route('/<series_id>', methods=['PUT', 'PATCH'])
def update_series(series_id: str):
    """Update a series."""
    data = request.get_json() or {}
    
    series = services.series.update(series_id, data)
    if not series:
        return jsonify({'error': 'Series not found'}), 404
    
    return jsonify(series.to_dict())


@bp.route('/<series_id>', methods=['DELETE'])
def delete_series(series_id: str):
    """Delete a series."""
    delete_episodes = request.args.get('delete_episodes', 'false').lower() == 'true'
    
    if services.series.delete(series_id, delete_episodes=delete_episodes):
        return jsonify({'success': True, 'message': 'Series deleted'})
    return jsonify({'error': 'Series not found'}), 404


@bp.route('/search', methods=['GET'])
def search_series():
    """Search series by name."""
    query = request.args.get('q', '')
    playlist_id = request.args.get('playlist_id')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400
    
    series_list = services.series.search(query, playlist_id, limit)
    
    return jsonify({
        'count': len(series_list),
        'series': [s.to_dict() for s in series_list]
    })


# Episodes

@bp.route('/<series_id>/episodes', methods=['GET'])
def get_episodes(series_id: str):
    """Get episodes for a series."""
    series = services.series.get(series_id)
    if not series:
        return jsonify({'error': 'Series not found'}), 404
    
    season = request.args.get('season')
    if season:
        season = int(season)
    
    from management.storage import storage
    episodes = storage.vod.get_series_episodes(series_id, season)
    
    return jsonify({
        'count': len(episodes),
        'episodes': [e.to_dict() for e in episodes]
    })


@bp.route('/<series_id>/episodes', methods=['POST'])
def add_episode(series_id: str):
    """Add a VOD item as an episode."""
    series = services.series.get(series_id)
    if not series:
        return jsonify({'error': 'Series not found'}), 404
    
    data = request.get_json() or {}
    vod_id = data.get('vod_id')
    
    if not vod_id:
        return jsonify({'error': 'vod_id is required'}), 400
    
    episode = services.series.add_episode(
        series_id=series_id,
        vod_id=vod_id,
        season=data.get('season'),
        episode=data.get('episode')
    )
    
    if not episode:
        return jsonify({'error': 'VOD not found'}), 404
    
    return jsonify(episode.to_dict())


@bp.route('/<series_id>/seasons', methods=['GET'])
def get_seasons(series_id: str):
    """Get seasons info for a series."""
    series = services.series.get(series_id)
    if not series:
        return jsonify({'error': 'Series not found'}), 404
    
    from management.storage import storage
    episodes = storage.vod.get_series_episodes(series_id)
    
    # Group by season
    seasons = {}
    for ep in episodes:
        season_num = ep.season or 0
        if season_num not in seasons:
            seasons[season_num] = {
                'season': season_num,
                'episode_count': 0,
                'episodes': []
            }
        seasons[season_num]['episode_count'] += 1
        seasons[season_num]['episodes'].append({
            'id': ep.id,
            'episode': ep.episode,
            'name': ep.name,
            'episode_title': ep.episode_title
        })
    
    # Sort seasons
    result = sorted(seasons.values(), key=lambda s: s['season'])
    
    return jsonify({
        'series_id': series_id,
        'season_count': len(result),
        'seasons': result
    })