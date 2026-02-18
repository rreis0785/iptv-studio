"""
Playlist parsers for multiple formats.

Parses M3U/M3U8, JSON, and XML playlist files into a standard
intermediate representation for import into the management backend.

Parsed Output Format:
    {
        'name': str,
        'epg_url': str or None,
        'groups': [{'name': str, ...}],
        'channels': [{'name': str, 'url': str, 'group_name': str, ...}],
        'vod': [{'name': str, 'url': str, ...}]
    }
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Parsed result type
# =============================================================================

class ParsedPlaylist:
    """Standard intermediate representation of a parsed playlist."""
    
    def __init__(
        self,
        name: str = 'Imported Playlist',
        epg_url: str = '',
        x_tvg_url: str = '',
        url_tvg: str = '',
    ):
        self.name = name
        self.epg_url = epg_url
        self.x_tvg_url = x_tvg_url
        self.url_tvg = url_tvg
        self.groups: List[Dict[str, Any]] = []
        self.channels: List[Dict[str, Any]] = []
        self.vod: List[Dict[str, Any]] = []
    
    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'epg_url': self.epg_url,
            'x_tvg_url': self.x_tvg_url,
            'url_tvg': self.url_tvg,
            'groups': self.groups,
            'channels': self.channels,
            'vod': self.vod,
        }
    
    @property
    def total_items(self) -> int:
        return len(self.channels) + len(self.vod)


# =============================================================================
# M3U / M3U8 Parser
# =============================================================================

# Regex to extract key="value" or key=value from EXTINF lines
_ATTR_PATTERN = re.compile(
    r'([\w-]+)\s*=\s*"([^"]*)"'  # key="value"
    r'|'
    r'([\w-]+)\s*=\s*(\S+)'       # key=value (unquoted)
)

# Regex to parse the EXTINF line: #EXTINF:duration attrs,title
_EXTINF_PATTERN = re.compile(
    r'#EXTINF:\s*(-?\d+)\s*(.*?)\s*,\s*(.*)\s*$'
)

# Header attribute pattern
_HEADER_ATTR_PATTERN = re.compile(
    r'([\w-]+)\s*=\s*"([^"]*)"'
)


class M3UParser:
    """
    Parser for M3U and M3U8 playlist format.
    
    Supports standard IPTV M3U attributes:
        tvg-id, tvg-name, tvg-logo, tvg-chno, tvg-shift,
        group-title, catchup, catchup-source, catchup-days
    
    Header attributes:
        x-tvg-url, url-tvg
    """
    
    @staticmethod
    def parse(content: str, name: str = None) -> ParsedPlaylist:
        """Parse M3U/M3U8 content."""
        lines = content.strip().splitlines()
        
        if not lines or not lines[0].strip().startswith('#EXTM3U'):
            raise ValueError('Invalid M3U format: missing #EXTM3U header')
        
        result = ParsedPlaylist(name=name or 'Imported Playlist')
        
        # Parse header attributes
        header_line = lines[0].strip()
        header_attrs = _parse_header(header_line)
        result.x_tvg_url = header_attrs.get('x-tvg-url', '')
        result.url_tvg = header_attrs.get('url-tvg', '')
        result.epg_url = result.x_tvg_url or result.url_tvg
        
        # Track unique groups
        seen_groups = set()
        
        # Parse entries
        i = 1
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and comments (non-EXTINF)
            if not line or (line.startswith('#') and not line.startswith('#EXTINF')):
                i += 1
                continue
            
            # Parse EXTINF line
            if line.startswith('#EXTINF'):
                match = _EXTINF_PATTERN.match(line)
                if not match:
                    i += 1
                    continue
                
                duration = int(match.group(1))
                attrs_str = match.group(2)
                title = match.group(3).strip()
                
                # Parse attributes
                attrs = _parse_attrs(attrs_str)
                
                # Get URL (next non-empty, non-comment line)
                url = ''
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if next_line and not next_line.startswith('#'):
                        url = next_line
                        break
                    i += 1
                
                if not url:
                    i += 1
                    continue
                
                # Track group
                group_name = attrs.get('group-title', '')
                if group_name and group_name not in seen_groups:
                    seen_groups.add(group_name)
                    result.groups.append({'name': group_name})
                
                # Build channel/VOD entry
                entry = {
                    'name': title,
                    'url': url,
                    'tvg_id': attrs.get('tvg-id', ''),
                    'tvg_name': attrs.get('tvg-name', ''),
                    'logo_url': attrs.get('tvg-logo', ''),
                    'group_name': group_name,
                }
                
                # Optional channel number
                if chno := attrs.get('tvg-chno', ''):
                    try:
                        entry['channel_number'] = int(chno)
                    except ValueError:
                        logger.debug("M3U: ignoring non-integer tvg-chno=%r", chno)

                # TVG shift
                if shift := attrs.get('tvg-shift', ''):
                    try:
                        entry['tvg_shift'] = int(shift)
                    except ValueError:
                        logger.debug("M3U: ignoring non-integer tvg-shift=%r", shift)

                # Catchup
                if catchup := attrs.get('catchup', ''):
                    entry['catchup_type'] = catchup
                    entry['catchup_source'] = attrs.get('catchup-source', '')
                    if days := attrs.get('catchup-days', ''):
                        try:
                            entry['catchup_days'] = int(days)
                        except ValueError:
                            logger.debug("M3U: ignoring non-integer catchup-days=%r", days)
                
                # VOD detection: negative duration or file extensions
                is_vod = _is_vod_url(url) or duration > 0
                
                if is_vod:
                    vod_entry = {
                        'name': title,
                        'url': url,
                        'logo_url': entry.get('logo_url', ''),
                        'group_name': group_name,
                    }
                    if duration > 0:
                        vod_entry['duration'] = duration
                    result.vod.append(vod_entry)
                else:
                    result.channels.append(entry)
            
            i += 1
        
        logger.info(
            f"M3U parsed: {len(result.channels)} channels, "
            f"{len(result.vod)} VOD, {len(result.groups)} groups"
        )
        return result


def _parse_header(header_line: str) -> Dict[str, str]:
    """Parse #EXTM3U header attributes."""
    attrs = {}
    # Remove '#EXTM3U' prefix
    rest = header_line[7:].strip()
    for match in _HEADER_ATTR_PATTERN.finditer(rest):
        key = match.group(1).lower()
        value = match.group(2)
        attrs[key] = value
    return attrs


def _parse_attrs(attrs_str: str) -> Dict[str, str]:
    """Parse EXTINF attribute string into a dict."""
    attrs = {}
    for match in _ATTR_PATTERN.finditer(attrs_str):
        if match.group(1):  # Quoted
            key = match.group(1).lower()
            value = match.group(2)
        else:  # Unquoted
            key = match.group(3).lower()
            value = match.group(4)
        attrs[key] = value
    return attrs


def _is_vod_url(url: str) -> bool:
    """Detect if a URL is likely VOD content."""
    vod_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')
    url_lower = url.lower().split('?')[0]  # Strip query params
    return any(url_lower.endswith(ext) for ext in vod_extensions)


# =============================================================================
# JSON Parser
# =============================================================================

class JSONParser:
    """
    Parser for JSON playlist format.
    
    Expected schema:
    {
        "name": "Playlist Name",
        "epg_url": "http://...",
        "groups": [{"name": "Sports", ...}],
        "channels": [{"name": "CNN", "url": "http://...", "group_name": "News", ...}],
        "vod": [{"name": "Movie", "url": "http://...", ...}]
    }
    """
    
    @staticmethod
    def parse(content: str, name: str = None) -> ParsedPlaylist:
        """Parse JSON playlist content."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f'Invalid JSON format: {e}')
        
        if not isinstance(data, dict):
            raise ValueError('JSON root must be an object')
        
        result = ParsedPlaylist(
            name=name or data.get('name', 'Imported Playlist'),
            epg_url=data.get('epg_url', ''),
            x_tvg_url=data.get('x_tvg_url', ''),
            url_tvg=data.get('url_tvg', ''),
        )
        
        # Parse groups
        for group_data in data.get('groups', []):
            if isinstance(group_data, str):
                result.groups.append({'name': group_data})
            elif isinstance(group_data, dict) and group_data.get('name'):
                result.groups.append(group_data)
        
        # Parse channels
        for ch_data in data.get('channels', []):
            if not isinstance(ch_data, dict):
                continue
            if not ch_data.get('name') or not ch_data.get('url'):
                continue
            result.channels.append(ch_data)
        
        # Parse VOD
        for vod_data in data.get('vod', []):
            if not isinstance(vod_data, dict):
                continue
            if not vod_data.get('name') or not vod_data.get('url'):
                continue
            result.vod.append(vod_data)
        
        logger.info(
            f"JSON parsed: {len(result.channels)} channels, "
            f"{len(result.vod)} VOD, {len(result.groups)} groups"
        )
        return result


# =============================================================================
# XML Parser
# =============================================================================

class XMLParser:
    """
    Parser for XML playlist format.
    
    Expected schema:
    <playlist name="..." epg_url="...">
        <groups>
            <group name="Sports" />
        </groups>
        <channels>
            <channel name="CNN" url="http://..." group="News"
                     tvg-id="..." tvg-logo="..." tvg-chno="..." />
        </channels>
        <vod>
            <item name="Movie" url="http://..." duration="7200" />
        </vod>
    </playlist>
    """
    
    @staticmethod
    def parse(content: str, name: str = None) -> ParsedPlaylist:
        """Parse XML playlist content."""
        try:
            root = ET.fromstring(content.strip())
        except ET.ParseError as e:
            raise ValueError(f'Invalid XML format: {e}')
        
        if root.tag != 'playlist':
            raise ValueError(f'Expected <playlist> root element, got <{root.tag}>')
        
        result = ParsedPlaylist(
            name=name or root.get('name', 'Imported Playlist'),
            epg_url=root.get('epg_url', ''),
            x_tvg_url=root.get('x_tvg_url', ''),
            url_tvg=root.get('url_tvg', ''),
        )
        
        # Parse groups
        groups_elem = root.find('groups')
        if groups_elem is not None:
            for group_elem in groups_elem.findall('group'):
                group_name = group_elem.get('name', '')
                if group_name:
                    group_data = {'name': group_name}
                    # Copy extra attributes
                    for key, value in group_elem.attrib.items():
                        if key != 'name':
                            group_data[key] = value
                    result.groups.append(group_data)
        
        # Parse channels
        channels_elem = root.find('channels')
        if channels_elem is not None:
            for ch_elem in channels_elem.findall('channel'):
                ch_name = ch_elem.get('name', '')
                ch_url = ch_elem.get('url', '') or (ch_elem.text or '').strip()
                
                if not ch_name or not ch_url:
                    continue
                
                entry = {
                    'name': ch_name,
                    'url': ch_url,
                    'tvg_id': ch_elem.get('tvg-id', ch_elem.get('tvg_id', '')),
                    'tvg_name': ch_elem.get('tvg-name', ch_elem.get('tvg_name', '')),
                    'logo_url': ch_elem.get('tvg-logo', ch_elem.get('logo_url', '')),
                    'group_name': ch_elem.get('group', ch_elem.get('group_name', '')),
                }
                
                if chno := ch_elem.get('tvg-chno', ch_elem.get('channel_number', '')):
                    try:
                        entry['channel_number'] = int(chno)
                    except ValueError:
                        logger.debug("XML: ignoring non-integer channel_number=%r", chno)

                if shift := ch_elem.get('tvg-shift', ch_elem.get('tvg_shift', '')):
                    try:
                        entry['tvg_shift'] = int(shift)
                    except ValueError:
                        logger.debug("XML: ignoring non-integer tvg_shift=%r", shift)
                
                result.channels.append(entry)
        
        # Parse VOD
        vod_elem = root.find('vod')
        if vod_elem is not None:
            for item_elem in vod_elem.findall('item'):
                item_name = item_elem.get('name', '')
                item_url = item_elem.get('url', '') or (item_elem.text or '').strip()
                
                if not item_name or not item_url:
                    continue
                
                vod_entry = {
                    'name': item_name,
                    'url': item_url,
                    'logo_url': item_elem.get('logo', item_elem.get('logo_url', '')),
                    'group_name': item_elem.get('group', item_elem.get('group_name', '')),
                }
                
                if duration := item_elem.get('duration', ''):
                    try:
                        vod_entry['duration'] = int(duration)
                    except ValueError:
                        logger.debug("XML: ignoring non-integer duration=%r", duration)

                if year := item_elem.get('year', ''):
                    try:
                        vod_entry['year'] = int(year)
                    except ValueError:
                        logger.debug("XML: ignoring non-integer year=%r", year)
                
                if plot := item_elem.get('plot', ''):
                    vod_entry['plot'] = plot
                
                result.vod.append(vod_entry)
        
        logger.info(
            f"XML parsed: {len(result.channels)} channels, "
            f"{len(result.vod)} VOD, {len(result.groups)} groups"
        )
        return result


# =============================================================================
# Format Auto-Detection & Factory
# =============================================================================

SUPPORTED_FORMATS = ('m3u', 'm3u8', 'json', 'xml')


def detect_format(content: str) -> str:
    """
    Auto-detect playlist format from content.
    
    Returns: 'm3u', 'json', or 'xml'
    """
    stripped = content.strip()
    
    if stripped.startswith('#EXTM3U'):
        return 'm3u'
    
    if stripped.startswith('{') or stripped.startswith('['):
        return 'json'
    
    if stripped.startswith('<'):
        return 'xml'
    
    # Fallback: try to detect M3U by #EXTINF presence
    if '#EXTINF' in stripped:
        return 'm3u'
    
    raise ValueError(
        'Cannot auto-detect format. '
        'Specify format parameter: m3u, json, or xml'
    )


def parse_playlist(
    content: str,
    format: str = None,
    name: str = None
) -> ParsedPlaylist:
    """
    Parse playlist content in any supported format.
    
    Args:
        content: Raw playlist content
        format: Format hint ('m3u', 'm3u8', 'json', 'xml'). Auto-detected if None.
        name: Override playlist name
    
    Returns:
        ParsedPlaylist with channels, groups, and VOD items
    """
    if format is None:
        format = detect_format(content)
    
    format = format.lower().strip()
    
    if format in ('m3u', 'm3u8'):
        return M3UParser.parse(content, name)
    elif format == 'json':
        return JSONParser.parse(content, name)
    elif format == 'xml':
        return XMLParser.parse(content, name)
    else:
        raise ValueError(f'Unsupported format: {format}. Use: m3u, m3u8, json, or xml')
