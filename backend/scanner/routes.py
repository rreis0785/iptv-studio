"""
Flask API routes for the media scanner.

Provides REST endpoints for scanning URLs and managing scan jobs.
"""

import asyncio
import logging
from flask import Blueprint, jsonify, request

from scanner.scanner import MediaScanner
from scanner.models import Platform

logger = logging.getLogger(__name__)

bp = Blueprint('scanner', __name__, url_prefix='/api/scanner')

# Global scanner instance
_scanner = MediaScanner()


def run_async(coro):
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@bp.route('/scan', methods=['POST'])
def scan_url():
    """
    Scan a URL for media content.
    
    Request Body:
        {
            "url": "https://youtube.com/@channel",
            "include_live": true,
            "include_vod": true,
            "max_items": 50,
            "max_depth": 2,
            "follow_links": true
        }
    
    Returns:
        ScanResult with discovered media items
    """
    data = request.get_json() or {}
    
    url = data.get('url')
    if not url:
        return jsonify({'error': 'url is required'}), 400
    
    try:
        result = run_async(_scanner.scan(
            url=url,
            include_live=data.get('include_live', True),
            include_vod=data.get('include_vod', True),
            max_items=data.get('max_items', 50),
            max_depth=data.get('max_depth', 2),
            follow_links=data.get('follow_links', True),
        ))
        
        return jsonify(result.to_dict())
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/scan/batch', methods=['POST'])
def scan_batch():
    """
    Scan multiple URLs.
    
    Request Body:
        {
            "urls": [
                "https://youtube.com/@channel1",
                "https://twitch.tv/streamer"
            ],
            "include_live": true,
            "include_vod": true,
            "max_items": 20
        }
    
    Returns:
        List of ScanResults
    """
    data = request.get_json() or {}
    
    urls = data.get('urls', [])
    if not urls:
        return jsonify({'error': 'urls array is required'}), 400
    
    if len(urls) > 10:
        return jsonify({'error': 'Maximum 10 URLs per batch'}), 400
    
    try:
        results = run_async(_scanner.scan_many(
            urls=urls,
            include_live=data.get('include_live', True),
            include_vod=data.get('include_vod', True),
            max_items=data.get('max_items', 20),
        ))
        
        return jsonify({
            'count': len(results),
            'results': [r.to_dict() for r in results]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/probe', methods=['GET', 'POST'])
def probe_url():
    """
    Probe a URL without full extraction.
    
    Query Parameters (GET) or JSON Body (POST):
        url: URL to probe
    
    Returns:
        URL info including platform and accessibility
    """
    if request.method == 'POST':
        data = request.get_json() or {}
        url = data.get('url')
    else:
        url = request.args.get('url')
    
    if not url:
        return jsonify({'error': 'url is required'}), 400
    
    try:
        info = run_async(_scanner.probe_url(url))
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/platforms', methods=['GET'])
def list_platforms():
    """
    List supported platforms.
    
    Returns:
        List of supported platform names
    """
    platforms = _scanner.get_supported_platforms()
    
    return jsonify({
        'count': len(platforms),
        'platforms': [p.value for p in platforms]
    })


@bp.route('/detect', methods=['GET'])
def detect_platform():
    """
    Detect the platform for a URL.
    
    Query Parameters:
        url: URL to analyze
    
    Returns:
        Detected platform
    """
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'url parameter is required'}), 400
    
    platform = _scanner.detect_platform(url)
    
    return jsonify({
        'url': url,
        'platform': platform.value
    })


@bp.route('/import', methods=['POST'])
def import_to_playlist():
    """
    Scan URL and import results to IPTV playlist.
    
    Request Body:
        {
            "url": "https://youtube.com/@channel",
            "playlist_id": "abc123",
            "group_id": "def456",
            "import_live": true,
            "import_vod": true,
            "max_items": 50
        }
    
    Returns:
        Import summary with created channels/VOD
    """
    data = request.get_json() or {}
    
    url = data.get('url')
    playlist_id = data.get('playlist_id')
    
    if not url:
        return jsonify({'error': 'url is required'}), 400
    if not playlist_id:
        return jsonify({'error': 'playlist_id is required'}), 400
    
    group_id = data.get('group_id')
    import_live = data.get('import_live', True)
    import_vod = data.get('import_vod', True)
    max_items = data.get('max_items', 50)
    
    try:
        # Scan the URL
        result = run_async(_scanner.scan(
            url=url,
            include_live=import_live,
            include_vod=import_vod,
            max_items=max_items,
        ))
        
        if not result.is_success:
            return jsonify({
                'error': 'Scan failed',
                'message': result.error_message
            }), 400
        
        # Convert to IPTV format
        channels_data = result.to_channels(playlist_id, group_id) if import_live else []
        vod_data = result.to_vod(playlist_id, group_id) if import_vod else []
        
        # Import using IPTV services (if available)
        channels_created = []
        vod_created = []
        
        try:
            from iptv.services import services
            
            for channel_data in channels_data:
                try:
                    channel = services.channels.create(**channel_data)
                    channels_created.append(channel.id)
                except Exception as e:
                    logger.warning(f"Failed to create channel: {e}")
            
            for vod_item in vod_data:
                try:
                    vod = services.vod.create(**vod_item)
                    vod_created.append(vod.id)
                except Exception as e:
                    logger.warning(f"Failed to create VOD: {e}")
                    
        except ImportError:
            # IPTV module not available, just return the data
            pass
        
        return jsonify({
            'success': True,
            'scan_result': {
                'url': url,
                'platform': result.platform.value,
                'items_found': result.item_count,
            },
            'imported': {
                'channels': len(channels_created),
                'vod': len(vod_created),
                'channel_ids': channels_created,
                'vod_ids': vod_created,
            },
            'channels_data': channels_data,
            'vod_data': vod_data,
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500