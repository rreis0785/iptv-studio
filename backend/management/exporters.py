"""
Playlist exporters for multiple formats.

Exports playlists to M3U/M3U8, JSON, and XML formats.
"""

import json
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Any, Dict, List, Optional

from management.models import Playlist, Channel, VOD, Group


def export_m3u(
    playlist: Playlist,
    channels: List[Channel],
    vods: List[VOD],
    groups: List[Group]
) -> str:
    """Export playlist as M3U."""
    lines = [playlist.to_m3u_header()]
    
    # Add channels
    for channel in channels:
        lines.append(channel.to_m3u_extinf())
        lines.append(channel.url)
    
    # Add VOD
    for vod in vods:
        # Construct simple EXTINF for VOD if not available on model
        duration = getattr(vod, 'duration', -1)
        logo = f' tvg-logo="{vod.logo_url}"' if vod.logo_url else ''
        group = f' group-title="{vod.group_name}"' if vod.group_name else ''
        lines.append(f'#EXTINF:{duration}{logo}{group},{vod.name}')
        lines.append(vod.url)
    
    return '\n'.join(lines)


def export_json(
    playlist: Playlist,
    channels: List[Channel],
    vods: List[VOD],
    groups: List[Group]
) -> str:
    """Export playlist as JSON."""
    data = {
        'name': playlist.name,
        'epg_url': playlist.epg_url,
        'x_tvg_url': playlist.x_tvg_url,
        'url_tvg': playlist.url_tvg,
        'groups': [g.to_dict() for g in groups],
        'channels': [c.to_dict() for c in channels],
        'vod': [v.to_dict() for v in vods],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def export_xml(
    playlist: Playlist,
    channels: List[Channel],
    vods: List[VOD],
    groups: List[Group]
) -> str:
    """Export playlist as XML."""
    root = ET.Element('playlist')
    root.set('name', playlist.name)
    if playlist.epg_url:
        root.set('epg_url', playlist.epg_url)
    if playlist.x_tvg_url:
        root.set('x_tvg_url', playlist.x_tvg_url)
    if playlist.url_tvg:
        root.set('url_tvg', playlist.url_tvg)
    
    # Groups
    groups_elem = ET.SubElement(root, 'groups')
    for group in groups:
        g_elem = ET.SubElement(groups_elem, 'group')
        g_elem.set('name', group.name)
        if group.is_hidden:
            g_elem.set('hidden', 'true')
    
    # Channels
    channels_elem = ET.SubElement(root, 'channels')
    for channel in channels:
        c_elem = ET.SubElement(channels_elem, 'channel')
        c_elem.set('name', channel.name)
        c_elem.set('url', channel.url)
        
        if channel.tvg_id:
            c_elem.set('tvg-id', channel.tvg_id)
        if channel.tvg_name:
            c_elem.set('tvg-name', channel.tvg_name)
        if channel.logo_url:
            c_elem.set('tvg-logo', channel.logo_url)
        if channel.channel_number:
            c_elem.set('tvg-chno', str(channel.channel_number))
        if channel.group_name:
            c_elem.set('group-title', channel.group_name)
        if channel.tvg_shift:
            c_elem.set('tvg-shift', str(channel.tvg_shift))
            
    # VOD
    vod_elem = ET.SubElement(root, 'vod')
    for vod in vods:
        v_elem = ET.SubElement(vod_elem, 'item')
        v_elem.set('name', vod.name)
        v_elem.set('url', vod.url)
        
        if vod.logo_url:
            v_elem.set('logo', vod.logo_url)
        if vod.group_name:
            v_elem.set('group', vod.group_name)
        
        # Add extra VOD metadata if available
        if hasattr(vod, 'duration') and vod.duration:
             v_elem.set('duration', str(vod.duration))
        if hasattr(vod, 'year') and vod.year:
             v_elem.set('year', str(vod.year))
        if hasattr(vod, 'plot') and vod.plot:
             v_elem.set('plot', vod.plot)

    # Pretty print
    xml_str = ET.tostring(root, encoding='utf-8')
    parsed = minidom.parseString(xml_str)
    return parsed.toprettyxml(indent='    ')
