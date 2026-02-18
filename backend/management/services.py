"""
Service layer for IPTV business logic.

This module contains service classes that encapsulate business logic
and coordinate between repositories and external operations.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from management.exporters import export_m3u, export_json, export_xml
from management.models import (
    Channel,
    CatchupType,
    ContentRating,
    EPGProgram,
    Group,
    Playlist,
    Series,
    StreamSource,
    StreamStatus,
    StreamType,
    VOD,
)
from management.parsers import parse_playlist
from management.storage import storage

logger = logging.getLogger(__name__)


# =============================================================================
# Playlist Service
# =============================================================================

class PlaylistService:
    """Service for playlist operations."""
    
    def create(
        self,
        name: str,
        description: str = None,
        url: str = None,
        epg_url: str = None,
        **kwargs
    ) -> Playlist:
        """Create a new playlist."""
        playlist = Playlist(
            name=name,
            description=description,
            url=url,
            epg_url=epg_url,
            **kwargs
        )
        
        # Set as default if first playlist
        if storage.playlists.count() == 0:
            playlist.is_default = True
        
        return storage.playlists.create(playlist)
    
    def get(self, id: str) -> Optional[Playlist]:
        """Get playlist by ID."""
        return storage.playlists.get(id)
    
    def get_all(self) -> List[Playlist]:
        """Get all playlists."""
        return storage.playlists.get_all()
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[Playlist]:
        """Update a playlist."""
        return storage.playlists.update(id, data)
    
    def delete(self, id: str, cascade: bool = True) -> bool:
        """
        Delete a playlist.
        
        Args:
            id: Playlist ID
            cascade: If True, delete all related channels, VOD, groups
        """
        playlist = storage.playlists.get(id)
        if not playlist:
            return False
        
        if cascade:
            # Delete related entities
            channels = storage.channels.find(playlist_id=id)
            for channel in channels:
                self._delete_channel_cascade(channel.id)
            
            vods = storage.vod.find(playlist_id=id)
            storage.vod.bulk_delete([v.id for v in vods])
            
            groups = storage.groups.find(playlist_id=id)
            storage.groups.bulk_delete([g.id for g in groups])
            
            series = storage.series.find(playlist_id=id)
            storage.series.bulk_delete([s.id for s in series])
        
        return storage.playlists.delete(id)
    
    def _delete_channel_cascade(self, channel_id: str) -> None:
        """Delete channel with related EPG and sources."""
        storage.epg.clear_channel(channel_id)
        sources = storage.sources.find(channel_id=channel_id)
        storage.sources.bulk_delete([s.id for s in sources])
        storage.channels.delete(channel_id)
    
    def get_with_stats(self, id: str) -> Optional[Dict[str, Any]]:
        """Get playlist with computed statistics."""
        playlist = storage.playlists.get(id)
        if not playlist:
            return None
        
        # Update counts
        playlist.channel_count = storage.channels.count(playlist_id=id)
        playlist.vod_count = storage.vod.count(playlist_id=id)
        playlist.group_count = storage.groups.count(playlist_id=id)
        playlist.series_count = storage.series.count(playlist_id=id)
        
        data = playlist.to_dict()
        data['groups'] = [g.to_dict() for g in storage.groups.get_by_playlist(id)]
        
        return data
    
    def set_default(self, id: str) -> bool:
        """Set playlist as default."""
        return storage.playlists.set_default(id)
    
    def import_playlist(
        self,
        content: str,
        format: str = None,
        name: str = None
    ) -> Dict[str, Any]:
        """Import a playlist from content."""
        # Parse content
        parsed = parse_playlist(content, format=format, name=name)
        
        # Create playlist
        playlist = self.create(
            name=parsed.name,
            epg_url=parsed.epg_url,
            x_tvg_url=parsed.x_tvg_url,
            url_tvg=parsed.url_tvg
        )
        
        # Create groups
        group_map = {}  # name -> id
        for group_data in parsed.groups:
            try:
                group = storage.groups.create(Group(
                    name=group_data['name'],
                    playlist_id=playlist.id,
                    order=len(group_map)
                ))
                group_map[group.name] = group.id
            except Exception:
                pass
        
        # Create channels
        created_channels = 0
        for i, ch_data in enumerate(parsed.channels):
            try:
                # Resolve group ID
                group_name = ch_data.pop('group_name', None)
                group_id = group_map.get(group_name) if group_name else None
                
                ch = Channel(
                    playlist_id=playlist.id,
                    group_id=group_id,
                    order=i,
                    **ch_data
                )
                storage.channels.create(ch)
                created_channels += 1
            except Exception as e:
                logger.warning(f"Failed to import channel {ch_data.get('name')}: {e}")
        
        # Create VOD
        created_vod = 0
        for v_data in parsed.vod:
            try:
                group_name = v_data.pop('group_name', None)
                group_id = group_map.get(group_name) if group_name else None
                
                v = VOD(
                    playlist_id=playlist.id,
                    group_id=group_id,
                    **v_data
                )
                storage.vod.create(v)
                created_vod += 1
            except Exception as e:
                logger.warning(f"Failed to import VOD {v_data.get('name')}: {e}")
        
        # Update counts
        playlist.channel_count = created_channels
        playlist.vod_count = created_vod
        playlist.group_count = len(group_map)
        playlist.touch()
        
        return {
            'playlist': playlist,
            'channels': created_channels,
            'vod': created_vod,
            'groups': len(group_map)
        }

    def export_playlist(
        self,
        id: str,
        format: str = 'm3u',
        include_vod: bool = False
    ) -> Optional[str]:
        """Export playlist in specified format."""
        playlist = storage.playlists.get(id)
        if not playlist:
            return None
        
        channels = storage.channels.get_by_playlist(id)
        groups = storage.groups.get_by_playlist(id)
        vods = []
        if include_vod:
            vods = storage.vod.get_by_playlist(id)
        
        format = format.lower()
        if format in ('m3u', 'm3u8'):
            return export_m3u(playlist, channels, vods, groups)
        elif format == 'json':
            return export_json(playlist, channels, vods, groups)
        elif format == 'xml':
            return export_xml(playlist, channels, vods, groups)
        else:
            raise ValueError(f"Unsupported export format: {format}")


# =============================================================================
# Channel Service
# =============================================================================

class ChannelService:
    """Service for channel operations."""
    
    def create(
        self,
        name: str,
        url: str,
        playlist_id: str,
        group_id: str = None,
        **kwargs
    ) -> Channel:
        """Create a new channel."""
        # Validate playlist exists
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        # Validate group exists if provided
        if group_id and not storage.groups.exists(group_id):
            raise ValueError(f"Group not found: {group_id}")
        
        # Set order to end of list
        existing = storage.channels.get_by_playlist(playlist_id)
        order = max((c.order for c in existing), default=-1) + 1
        
        channel = Channel(
            name=name,
            url=url,
            playlist_id=playlist_id,
            group_id=group_id,
            order=order,
            **kwargs
        )
        
        created = storage.channels.create(channel)
        
        # Update playlist count
        playlist = storage.playlists.get(playlist_id)
        if playlist:
            playlist.channel_count = storage.channels.count(playlist_id=playlist_id)
            playlist.touch()
        
        return created
    
    def get(self, id: str, include_epg: bool = False) -> Optional[Channel]:
        """Get channel by ID."""
        channel = storage.channels.get(id)
        if channel and include_epg:
            channel.current_program = storage.epg.get_current(id)
            channel.group = storage.groups.get(channel.group_id) if channel.group_id else None
            channel.sources = storage.sources.get_by_channel(id)
        return channel
    
    def get_all(
        self,
        playlist_id: str = None,
        group_id: str = None,
        include_hidden: bool = False
    ) -> List[Channel]:
        """Get all channels with optional filtering."""
        if playlist_id:
            return storage.channels.get_by_playlist(
                playlist_id,
                group_id=group_id,
                include_hidden=include_hidden
            )
        return storage.channels.get_all()
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[Channel]:
        """Update a channel."""
        # Validate group if changing
        if 'group_id' in data and data['group_id']:
            if not storage.groups.exists(data['group_id']):
                raise ValueError(f"Group not found: {data['group_id']}")
        
        return storage.channels.update(id, data)
    
    def delete(self, id: str) -> bool:
        """Delete a channel and related data."""
        channel = storage.channels.get(id)
        if not channel:
            return False
        
        # Delete related EPG
        storage.epg.clear_channel(id)
        
        # Delete related sources
        sources = storage.sources.find(channel_id=id)
        storage.sources.bulk_delete([s.id for s in sources])
        
        # Update playlist count
        playlist = storage.playlists.get(channel.playlist_id)
        if playlist:
            playlist.channel_count = max(0, playlist.channel_count - 1)
            playlist.touch()
        
        return storage.channels.delete(id)
    
    def search(
        self,
        query: str,
        playlist_id: str = None,
        limit: int = 50
    ) -> List[Channel]:
        """Search channels by name."""
        return storage.channels.search(query, playlist_id, limit)
    
    def get_favorites(self, playlist_id: str = None) -> List[Channel]:
        """Get favorite channels."""
        return storage.channels.get_favorites(playlist_id)
    
    def toggle_favorite(self, id: str) -> Optional[Channel]:
        """Toggle channel favorite status."""
        channel = storage.channels.get(id)
        if channel:
            return storage.channels.update(id, {'is_favorite': not channel.is_favorite})
        return None
    
    def reorder(self, channel_ids: List[str]) -> int:
        """Reorder channels."""
        return storage.channels.reorder(channel_ids)
    
    def move_to_group(self, channel_ids: List[str], group_id: str) -> int:
        """Move channels to a group."""
        if group_id and not storage.groups.exists(group_id):
            raise ValueError(f"Group not found: {group_id}")
        
        updated = 0
        for channel_id in channel_ids:
            if storage.channels.update(channel_id, {'group_id': group_id}):
                updated += 1
        return updated
    
    def bulk_delete(self, channel_ids: List[str]) -> int:
        """Delete multiple channels."""
        deleted = 0
        for channel_id in channel_ids:
            if self.delete(channel_id):
                deleted += 1
        return deleted
    
    def bulk_create(
        self,
        channels_data: List[Dict[str, Any]],
        playlist_id: str
    ) -> Tuple[List[Channel], List[Dict[str, Any]]]:
        """
        Create multiple channels.
        
        Returns:
            Tuple of (created_channels, errors)
        """
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        created = []
        errors = []
        
        for i, data in enumerate(channels_data):
            try:
                data['playlist_id'] = playlist_id
                name = data.pop('name', '')
                url = data.pop('url', '')
                if not name or not url:
                    errors.append({'index': i, 'error': 'name and url are required'})
                    continue
                channel = self.create(name=name, url=url, **data)
                created.append(channel)
            except Exception as e:
                errors.append({'index': i, 'error': str(e)})
        
        return created, errors
    
    def bulk_update(
        self,
        updates: List[Dict[str, Any]]
    ) -> Tuple[List[Channel], List[Dict[str, Any]]]:
        """
        Update multiple channels.
        
        Each dict must have 'id' plus fields to update.
        
        Returns:
            Tuple of (updated_channels, errors)
        """
        updated = []
        errors = []
        
        for i, data in enumerate(updates):
            channel_id = data.pop('id', None)
            if not channel_id:
                errors.append({'index': i, 'error': 'id is required'})
                continue
            try:
                channel = self.update(channel_id, data)
                if channel:
                    updated.append(channel)
                else:
                    errors.append({'index': i, 'id': channel_id, 'error': 'Channel not found'})
            except Exception as e:
                errors.append({'index': i, 'id': channel_id, 'error': str(e)})
        
        return updated, errors


# =============================================================================
# VOD Service
# =============================================================================

class VODService:
    """Service for VOD operations."""
    
    def create(
        self,
        name: str,
        url: str,
        playlist_id: str,
        group_id: str = None,
        content_type: str = "movie",
        **kwargs
    ) -> VOD:
        """Create a new VOD item."""
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        if group_id and not storage.groups.exists(group_id):
            raise ValueError(f"Group not found: {group_id}")
        
        vod = VOD(
            name=name,
            url=url,
            playlist_id=playlist_id,
            group_id=group_id,
            content_type=content_type,
            **kwargs
        )
        
        created = storage.vod.create(vod)
        
        # Update playlist count
        playlist = storage.playlists.get(playlist_id)
        if playlist:
            playlist.vod_count = storage.vod.count(playlist_id=playlist_id)
            playlist.touch()
        
        return created
    
    def get(self, id: str) -> Optional[VOD]:
        """Get VOD by ID."""
        vod = storage.vod.get(id)
        if vod:
            vod.group = storage.groups.get(vod.group_id) if vod.group_id else None
            vod.sources = storage.sources.get_by_channel(id)
        return vod
    
    def get_all(
        self,
        playlist_id: str = None,
        group_id: str = None,
        content_type: str = None,
        include_hidden: bool = False
    ) -> List[VOD]:
        """Get all VOD items with optional filtering."""
        if playlist_id:
            return storage.vod.get_by_playlist(
                playlist_id,
                group_id=group_id,
                content_type=content_type,
                include_hidden=include_hidden
            )
        return storage.vod.get_all()
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[VOD]:
        """Update a VOD item."""
        if 'group_id' in data and data['group_id']:
            if not storage.groups.exists(data['group_id']):
                raise ValueError(f"Group not found: {data['group_id']}")
        
        return storage.vod.update(id, data)
    
    def delete(self, id: str) -> bool:
        """Delete a VOD item."""
        vod = storage.vod.get(id)
        if not vod:
            return False
        
        # Delete sources
        sources = storage.sources.find(channel_id=id)
        storage.sources.bulk_delete([s.id for s in sources])
        
        # Update playlist count
        playlist = storage.playlists.get(vod.playlist_id)
        if playlist:
            playlist.vod_count = max(0, playlist.vod_count - 1)
            playlist.touch()
        
        return storage.vod.delete(id)
    
    def search(
        self,
        query: str,
        playlist_id: str = None,
        content_type: str = None,
        limit: int = 50
    ) -> List[VOD]:
        """Search VOD by name or plot."""
        return storage.vod.search(query, playlist_id, content_type, limit)
    
    def get_continue_watching(
        self,
        playlist_id: str = None,
        limit: int = 20
    ) -> List[VOD]:
        """Get in-progress VOD items."""
        return storage.vod.get_continue_watching(playlist_id, limit)
    
    def get_recently_watched(
        self,
        playlist_id: str = None,
        limit: int = 20
    ) -> List[VOD]:
        """Get recently watched VOD items."""
        return storage.vod.get_recently_watched(playlist_id, limit)
    
    def update_watch_progress(
        self,
        id: str,
        position: int,
        completed: bool = None
    ) -> Optional[VOD]:
        """Update watch progress."""
        vod = storage.vod.get(id)
        if not vod:
            return None
        
        data = {
            'watch_position': position,
            'last_watched': datetime.now(timezone.utc),
        }
        
        if completed is not None:
            data['watch_completed'] = completed
        elif vod.duration and position >= vod.duration * 0.95:
            data['watch_completed'] = True
        
        return storage.vod.update(id, data)
    
    def toggle_favorite(self, id: str) -> Optional[VOD]:
        """Toggle VOD favorite status."""
        vod = storage.vod.get(id)
        if vod:
            return storage.vod.update(id, {'is_favorite': not vod.is_favorite})
        return None
    
    def bulk_delete(self, vod_ids: List[str]) -> int:
        """Delete multiple VOD items."""
        deleted = 0
        for vod_id in vod_ids:
            if self.delete(vod_id):
                deleted += 1
        return deleted
    
    def bulk_create(
        self,
        vods_data: List[Dict[str, Any]],
        playlist_id: str
    ) -> Tuple[List[VOD], List[Dict[str, Any]]]:
        """
        Create multiple VOD items.
        
        Returns:
            Tuple of (created_vods, errors)
        """
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        created = []
        errors = []
        
        for i, data in enumerate(vods_data):
            try:
                data['playlist_id'] = playlist_id
                name = data.pop('name', '')
                url = data.pop('url', '')
                if not name or not url:
                    errors.append({'index': i, 'error': 'name and url are required'})
                    continue
                vod = self.create(name=name, url=url, **data)
                created.append(vod)
            except Exception as e:
                errors.append({'index': i, 'error': str(e)})
        
        return created, errors
    
    def bulk_update(
        self,
        updates: List[Dict[str, Any]]
    ) -> Tuple[List[VOD], List[Dict[str, Any]]]:
        """
        Update multiple VOD items.
        
        Returns:
            Tuple of (updated_vods, errors)
        """
        updated = []
        errors = []
        
        for i, data in enumerate(updates):
            vod_id = data.pop('id', None)
            if not vod_id:
                errors.append({'index': i, 'error': 'id is required'})
                continue
            try:
                vod = self.update(vod_id, data)
                if vod:
                    updated.append(vod)
                else:
                    errors.append({'index': i, 'id': vod_id, 'error': 'VOD not found'})
            except Exception as e:
                errors.append({'index': i, 'id': vod_id, 'error': str(e)})
        
        return updated, errors


# =============================================================================
# Group Service
# =============================================================================

class GroupService:
    """Service for group operations."""
    
    def create(
        self,
        name: str,
        playlist_id: str,
        **kwargs
    ) -> Group:
        """Create a new group."""
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        # Set order
        existing = storage.groups.get_by_playlist(playlist_id)
        order = max((g.order for g in existing), default=-1) + 1
        
        group = Group(
            name=name,
            playlist_id=playlist_id,
            order=order,
            **kwargs
        )
        
        created = storage.groups.create(group)
        
        # Update playlist count
        playlist = storage.playlists.get(playlist_id)
        if playlist:
            playlist.group_count = storage.groups.count(playlist_id=playlist_id)
            playlist.touch()
        
        return created
    
    def get(self, id: str, include_counts: bool = True) -> Optional[Group]:
        """Get group by ID."""
        group = storage.groups.get(id)
        if group and include_counts:
            group.channel_count = storage.channels.count(group_id=id)
            group.vod_count = storage.vod.count(group_id=id)
        return group
    
    def get_all(
        self,
        playlist_id: str = None,
        include_hidden: bool = False
    ) -> List[Group]:
        """Get all groups."""
        if playlist_id:
            return storage.groups.get_by_playlist(playlist_id, include_hidden)
        return storage.groups.get_all()
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[Group]:
        """Update a group."""
        return storage.groups.update(id, data)
    
    def delete(self, id: str, move_to_group: str = None) -> bool:
        """
        Delete a group.
        
        Args:
            id: Group ID to delete
            move_to_group: Move channels/VOD to this group (None = ungroup)
        """
        group = storage.groups.get(id)
        if not group:
            return False
        
        # Move or ungroup channels
        channels = storage.channels.find(group_id=id)
        for channel in channels:
            storage.channels.update(channel.id, {'group_id': move_to_group})
        
        # Move or ungroup VOD
        vods = storage.vod.find(group_id=id)
        for vod in vods:
            storage.vod.update(vod.id, {'group_id': move_to_group})
        
        # Update playlist count
        playlist = storage.playlists.get(group.playlist_id)
        if playlist:
            playlist.group_count = max(0, playlist.group_count - 1)
            playlist.touch()
        
        return storage.groups.delete(id)
    
    def reorder(self, group_ids: List[str]) -> int:
        """Reorder groups."""
        return storage.groups.reorder(group_ids)
    
    def merge(self, source_id: str, target_id: str) -> bool:
        """Merge source group into target group."""
        source = storage.groups.get(source_id)
        target = storage.groups.get(target_id)
        
        if not source or not target:
            return False
        
        # Move channels
        channels = storage.channels.find(group_id=source_id)
        for channel in channels:
            storage.channels.update(channel.id, {'group_id': target_id})
        
        # Move VOD
        vods = storage.vod.find(group_id=source_id)
        for vod in vods:
            storage.vod.update(vod.id, {'group_id': target_id})
        
        # Delete source group
        return self.delete(source_id)
    
    def bulk_create(
        self,
        groups_data: List[Dict[str, Any]],
        playlist_id: str
    ) -> Tuple[List[Group], List[Dict[str, Any]]]:
        """
        Create multiple groups.
        
        Returns:
            Tuple of (created_groups, errors)
        """
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        created = []
        errors = []
        
        for i, data in enumerate(groups_data):
            try:
                data['playlist_id'] = playlist_id
                name = data.pop('name', '')
                if not name:
                    errors.append({'index': i, 'error': 'name is required'})
                    continue
                group = self.create(name=name, **data)
                created.append(group)
            except Exception as e:
                errors.append({'index': i, 'error': str(e)})
        
        return created, errors


# =============================================================================
# EPG Service
# =============================================================================

class EPGService:
    """Service for EPG operations."""
    
    def create(
        self,
        channel_id: str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        **kwargs
    ) -> EPGProgram:
        """Create a new EPG program."""
        if not storage.channels.exists(channel_id):
            raise ValueError(f"Channel not found: {channel_id}")
        
        program = EPGProgram(
            channel_id=channel_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            **kwargs
        )
        
        return storage.epg.create(program)
    
    def get(self, id: str) -> Optional[EPGProgram]:
        """Get EPG program by ID."""
        return storage.epg.get(id)
    
    def get_by_channel(
        self,
        channel_id: str,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 100
    ) -> List[EPGProgram]:
        """Get EPG programs for a channel."""
        return storage.epg.get_by_channel(channel_id, start_time, end_time, limit)
    
    def get_current(self, channel_id: str) -> Optional[EPGProgram]:
        """Get currently airing program."""
        return storage.epg.get_current(channel_id)
    
    def get_schedule(
        self,
        channel_id: str,
        date: datetime = None
    ) -> List[EPGProgram]:
        """Get full day schedule for a channel."""
        if date is None:
            date = datetime.now(timezone.utc)
        
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        
        return self.get_by_channel(channel_id, start, end, limit=200)
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[EPGProgram]:
        """Update an EPG program."""
        return storage.epg.update(id, data)
    
    def delete(self, id: str) -> bool:
        """Delete an EPG program."""
        return storage.epg.delete(id)
    
    def bulk_create(self, programs: List[Dict[str, Any]]) -> List[EPGProgram]:
        """Create multiple EPG programs."""
        created = []
        for prog_data in programs:
            try:
                program = EPGProgram(**prog_data)
                storage.epg.create(program)
                created.append(program)
            except Exception as e:
                logger.warning(f"Failed to create EPG program: {e}")
        return created
    
    def clear_channel(self, channel_id: str) -> int:
        """Clear all EPG data for a channel."""
        return storage.epg.clear_channel(channel_id)
    
    def clear_old(self, before: datetime = None) -> int:
        """Clear old EPG data."""
        return storage.epg.clear_old(before)


# =============================================================================
# Series Service
# =============================================================================

class SeriesService:
    """Service for series operations."""
    
    def create(
        self,
        name: str,
        playlist_id: str,
        **kwargs
    ) -> Series:
        """Create a new series."""
        if not storage.playlists.exists(playlist_id):
            raise ValueError(f"Playlist not found: {playlist_id}")
        
        series = Series(
            name=name,
            playlist_id=playlist_id,
            **kwargs
        )
        
        created = storage.series.create(series)
        
        # Update playlist count
        playlist = storage.playlists.get(playlist_id)
        if playlist:
            playlist.series_count = storage.series.count(playlist_id=playlist_id)
            playlist.touch()
        
        return created
    
    def get(self, id: str, include_episodes: bool = False) -> Optional[Series]:
        """Get series by ID."""
        series = storage.series.get(id)
        if series and include_episodes:
            series.episodes = storage.vod.get_series_episodes(id)
            series.episodes_count = len(series.episodes)
        return series
    
    def get_all(self, playlist_id: str = None) -> List[Series]:
        """Get all series."""
        if playlist_id:
            return storage.series.get_by_playlist(playlist_id)
        return storage.series.get_all()
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[Series]:
        """Update a series."""
        return storage.series.update(id, data)
    
    def delete(self, id: str, delete_episodes: bool = False) -> bool:
        """Delete a series."""
        series = storage.series.get(id)
        if not series:
            return False
        
        if delete_episodes:
            episodes = storage.vod.get_series_episodes(id)
            storage.vod.bulk_delete([e.id for e in episodes])
        else:
            # Unlink episodes
            episodes = storage.vod.get_series_episodes(id)
            for episode in episodes:
                storage.vod.update(episode.id, {'series_id': None})
        
        # Update playlist count
        playlist = storage.playlists.get(series.playlist_id)
        if playlist:
            playlist.series_count = max(0, playlist.series_count - 1)
            playlist.touch()
        
        return storage.series.delete(id)
    
    def add_episode(
        self,
        series_id: str,
        vod_id: str,
        season: int = None,
        episode: int = None
    ) -> Optional[VOD]:
        """Add a VOD item as an episode of a series."""
        series = storage.series.get(series_id)
        vod = storage.vod.get(vod_id)
        
        if not series or not vod:
            return None
        
        data = {
            'series_id': series_id,
            'series_name': series.name,
            'content_type': 'episode',
        }
        if season is not None:
            data['season'] = season
        if episode is not None:
            data['episode'] = episode
        
        return storage.vod.update(vod_id, data)
    
    def search(
        self,
        query: str,
        playlist_id: str = None,
        limit: int = 50
    ) -> List[Series]:
        """Search series by name."""
        return storage.series.search(query, playlist_id, limit)


# =============================================================================
# Source Service
# =============================================================================

class SourceService:
    """Service for stream source operations."""
    
    def create(
        self,
        channel_id: str,
        url: str,
        **kwargs
    ) -> StreamSource:
        """Create a new stream source."""
        # Check if channel or VOD exists
        if not storage.channels.exists(channel_id) and not storage.vod.exists(channel_id):
            raise ValueError(f"Channel/VOD not found: {channel_id}")
        
        # Set priority
        existing = storage.sources.get_by_channel(channel_id)
        priority = max((s.priority for s in existing), default=-1) + 1
        
        # Set as primary if first source
        is_primary = len(existing) == 0
        
        source = StreamSource(
            channel_id=channel_id,
            url=url,
            priority=priority,
            is_primary=is_primary,
            **kwargs
        )
        
        return storage.sources.create(source)
    
    def get(self, id: str) -> Optional[StreamSource]:
        """Get source by ID."""
        return storage.sources.get(id)
    
    def get_by_channel(self, channel_id: str) -> List[StreamSource]:
        """Get all sources for a channel."""
        return storage.sources.get_by_channel(channel_id)
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[StreamSource]:
        """Update a source."""
        return storage.sources.update(id, data)
    
    def delete(self, id: str) -> bool:
        """Delete a source."""
        source = storage.sources.get(id)
        if not source:
            return False
        
        was_primary = source.is_primary
        deleted = storage.sources.delete(id)
        
        # If deleted primary, set new primary
        if deleted and was_primary:
            remaining = storage.sources.get_by_channel(source.channel_id)
            if remaining:
                storage.sources.update(remaining[0].id, {'is_primary': True})
        
        return deleted
    
    def set_primary(self, id: str) -> bool:
        """Set a source as primary."""
        source = storage.sources.get(id)
        if not source:
            return False
        
        # Unset current primary
        for s in storage.sources.get_by_channel(source.channel_id):
            if s.is_primary and s.id != id:
                storage.sources.update(s.id, {'is_primary': False})
        
        storage.sources.update(id, {'is_primary': True})
        return True


# =============================================================================
# Service Factory
# =============================================================================

class Services:
    """Container for all services."""
    
    def __init__(self):
        self.playlists = PlaylistService()
        self.channels = ChannelService()
        self.vod = VODService()
        self.groups = GroupService()
        self.epg = EPGService()
        self.series = SeriesService()
        self.sources = SourceService()


# Global services instance
services = Services()