"""
Storage implementation for IPTV entities.

This module provides a repository pattern for storing and retrieving
IPTV entities. Supports in-memory storage and JSON file persistence.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock, Timer
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar

from management.models import (
    BaseModel,
    Channel,
    EPGProgram,
    Group,
    Playlist,
    Series,
    StreamSource,
    VOD,
)

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


# =============================================================================
# Abstract Repository
# =============================================================================

class Repository(ABC, Generic[T]):
    """Abstract base repository interface."""
    
    @abstractmethod
    def create(self, entity: T) -> T:
        """Create a new entity."""
        pass
    
    @abstractmethod
    def get(self, id: str) -> Optional[T]:
        """Get entity by ID."""
        pass
    
    @abstractmethod
    def get_all(self) -> List[T]:
        """Get all entities."""
        pass
    
    @abstractmethod
    def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        """Update entity by ID."""
        pass
    
    @abstractmethod
    def delete(self, id: str) -> bool:
        """Delete entity by ID."""
        pass
    
    @abstractmethod
    def find(self, **kwargs) -> List[T]:
        """Find entities matching criteria."""
        pass
    
    @abstractmethod
    def count(self, **kwargs) -> int:
        """Count entities matching criteria."""
        pass


# =============================================================================
# In-Memory Repository Implementation
# =============================================================================

class InMemoryRepository(Repository[T]):
    """
    Thread-safe in-memory repository implementation.
    
    Provides CRUD operations with filtering, pagination, and sorting.
    """
    
    def __init__(self, model_class: Type[T]):
        self._model_class = model_class
        self._data: Dict[str, T] = {}
        self._lock = RLock()
    
    def create(self, entity: T) -> T:
        """Create a new entity."""
        with self._lock:
            if entity.id in self._data:
                raise ValueError(f"Entity with ID {entity.id} already exists")
            self._data[entity.id] = entity
            logger.debug(f"Created {self._model_class.__name__}: {entity.id}")
            return entity
    
    def get(self, id: str) -> Optional[T]:
        """Get entity by ID."""
        with self._lock:
            return self._data.get(id)
    
    def get_all(self) -> List[T]:
        """Get all entities."""
        with self._lock:
            return list(self._data.values())
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        """Update entity by ID."""
        with self._lock:
            entity = self._data.get(id)
            if not entity:
                return None
            
            entity.update(**data)
            logger.debug(f"Updated {self._model_class.__name__}: {id}")
            return entity
    
    def delete(self, id: str) -> bool:
        """Delete entity by ID."""
        with self._lock:
            if id in self._data:
                del self._data[id]
                logger.debug(f"Deleted {self._model_class.__name__}: {id}")
                return True
            return False
    
    def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        order_desc: bool = False,
        limit: int = None,
        offset: int = 0,
        **kwargs
    ) -> List[T]:
        """
        Find entities matching criteria.
        
        Args:
            filters: Dict of field -> value filters
            order_by: Field name to sort by
            order_desc: Sort descending
            limit: Maximum results
            offset: Skip first N results
            **kwargs: Additional filters
        """
        with self._lock:
            # Combine filters
            all_filters = {**(filters or {}), **kwargs}
            
            # Filter entities
            results = []
            for entity in self._data.values():
                if self._matches_filters(entity, all_filters):
                    results.append(entity)
            
            # Sort
            if order_by:
                results.sort(
                    key=lambda e: getattr(e, order_by, None) or '',
                    reverse=order_desc
                )
            
            # Paginate
            if offset:
                results = results[offset:]
            if limit:
                results = results[:limit]
            
            return results
    
    def _matches_filters(self, entity: T, filters: Dict[str, Any]) -> bool:
        """Check if entity matches all filters."""
        for field, value in filters.items():
            entity_value = getattr(entity, field, None)
            
            # Handle None
            if value is None:
                if entity_value is not None:
                    return False
                continue
            
            # Handle list membership
            if isinstance(value, list):
                if entity_value not in value:
                    return False
                continue
            
            # Handle callable (custom filter)
            if callable(value):
                if not value(entity_value):
                    return False
                continue
            
            # Direct comparison
            if entity_value != value:
                return False
        
        return True
    
    def count(self, **kwargs) -> int:
        """Count entities matching criteria."""
        if not kwargs:
            with self._lock:
                return len(self._data)
        return len(self.find(**kwargs))
    
    def exists(self, id: str) -> bool:
        """Check if entity exists."""
        with self._lock:
            return id in self._data
    
    def clear(self) -> int:
        """Clear all entities. Returns count of deleted."""
        with self._lock:
            count = len(self._data)
            self._data.clear()
            return count
    
    def bulk_create(self, entities: List[T]) -> List[T]:
        """Create multiple entities."""
        with self._lock:
            created = []
            for entity in entities:
                if entity.id not in self._data:
                    self._data[entity.id] = entity
                    created.append(entity)
            return created
    
    def bulk_delete(self, ids: List[str]) -> int:
        """Delete multiple entities. Returns count of deleted."""
        with self._lock:
            deleted = 0
            for id in ids:
                if id in self._data:
                    del self._data[id]
                    deleted += 1
            return deleted


# =============================================================================
# Specialized Repositories
# =============================================================================

class PlaylistRepository(InMemoryRepository[Playlist]):
    """Repository for Playlist entities."""
    
    def __init__(self):
        super().__init__(Playlist)
    
    def get_default(self) -> Optional[Playlist]:
        """Get the default playlist."""
        results = self.find(is_default=True, limit=1)
        return results[0] if results else None
    
    def set_default(self, id: str) -> bool:
        """Set a playlist as default (unsets others)."""
        with self._lock:
            playlist = self.get(id)
            if not playlist:
                return False
            
            # Unset current default
            for p in self._data.values():
                if p.is_default and p.id != id:
                    p.is_default = False
                    p.touch()
            
            # Set new default
            playlist.is_default = True
            playlist.touch()
            return True


class ChannelRepository(InMemoryRepository[Channel]):
    """Repository for Channel entities."""
    
    def __init__(self):
        super().__init__(Channel)
    
    def get_by_playlist(
        self,
        playlist_id: str,
        group_id: str = None,
        include_hidden: bool = False,
        order_by: str = 'order'
    ) -> List[Channel]:
        """Get channels for a playlist."""
        filters = {'playlist_id': playlist_id}
        if group_id:
            filters['group_id'] = group_id
        if not include_hidden:
            filters['is_hidden'] = False
        
        return self.find(filters=filters, order_by=order_by)
    
    def get_favorites(self, playlist_id: str = None) -> List[Channel]:
        """Get favorite channels."""
        filters = {'is_favorite': True}
        if playlist_id:
            filters['playlist_id'] = playlist_id
        return self.find(filters=filters)
    
    def search(
        self,
        query: str,
        playlist_id: str = None,
        limit: int = 50
    ) -> List[Channel]:
        """Search channels by name."""
        query_lower = query.lower()
        
        def name_matches(entity):
            return query_lower in entity.name.lower()
        
        filters = {}
        if playlist_id:
            filters['playlist_id'] = playlist_id
        
        with self._lock:
            results = []
            for channel in self._data.values():
                if name_matches(channel):
                    if not filters or self._matches_filters(channel, filters):
                        results.append(channel)
                        if len(results) >= limit:
                            break
            return results
    
    def reorder(self, channel_ids: List[str]) -> int:
        """Reorder channels by ID list. Returns count updated."""
        with self._lock:
            updated = 0
            for order, channel_id in enumerate(channel_ids):
                channel = self._data.get(channel_id)
                if channel:
                    channel.order = order
                    channel.touch()
                    updated += 1
            return updated


class VODRepository(InMemoryRepository[VOD]):
    """Repository for VOD entities."""
    
    def __init__(self):
        super().__init__(VOD)
    
    def get_by_playlist(
        self,
        playlist_id: str,
        group_id: str = None,
        content_type: str = None,
        include_hidden: bool = False
    ) -> List[VOD]:
        """Get VOD items for a playlist."""
        filters = {'playlist_id': playlist_id}
        if group_id:
            filters['group_id'] = group_id
        if content_type:
            filters['content_type'] = content_type
        if not include_hidden:
            filters['is_hidden'] = False
        
        return self.find(filters=filters, order_by='name')
    
    def get_series_episodes(
        self,
        series_id: str,
        season: int = None
    ) -> List[VOD]:
        """Get episodes for a series."""
        filters = {'series_id': series_id}
        if season:
            filters['season'] = season
        return self.find(filters=filters, order_by='episode')
    
    def get_recently_watched(
        self,
        playlist_id: str = None,
        limit: int = 20
    ) -> List[VOD]:
        """Get recently watched VOD items."""
        def has_progress(entity):
            return entity.watch_position > 0 or entity.last_watched
        
        results = self.find(
            filters={'playlist_id': playlist_id} if playlist_id else None,
            order_by='last_watched',
            order_desc=True,
            limit=limit * 2  # Get extra to filter
        )
        
        return [v for v in results if has_progress(v)][:limit]
    
    def get_continue_watching(
        self,
        playlist_id: str = None,
        limit: int = 20
    ) -> List[VOD]:
        """Get in-progress VOD items."""
        def in_progress(entity):
            return (
                entity.watch_position > 0 and
                not entity.watch_completed and
                entity.watch_progress_percent < 95
            )
        
        results = self.find(
            filters={'playlist_id': playlist_id} if playlist_id else None,
            order_by='last_watched',
            order_desc=True
        )
        
        return [v for v in results if in_progress(v)][:limit]
    
    def search(
        self,
        query: str,
        playlist_id: str = None,
        content_type: str = None,
        limit: int = 50
    ) -> List[VOD]:
        """Search VOD by name or plot."""
        query_lower = query.lower()
        
        def matches(entity):
            if query_lower in entity.name.lower():
                return True
            if entity.plot and query_lower in entity.plot.lower():
                return True
            return False
        
        filters = {}
        if playlist_id:
            filters['playlist_id'] = playlist_id
        if content_type:
            filters['content_type'] = content_type
        
        with self._lock:
            results = []
            for vod in self._data.values():
                if matches(vod):
                    if not filters or self._matches_filters(vod, filters):
                        results.append(vod)
                        if len(results) >= limit:
                            break
            return results


class GroupRepository(InMemoryRepository[Group]):
    """Repository for Group entities."""
    
    def __init__(self):
        super().__init__(Group)
    
    def get_by_playlist(
        self,
        playlist_id: str,
        include_hidden: bool = False
    ) -> List[Group]:
        """Get groups for a playlist."""
        filters = {'playlist_id': playlist_id}
        if not include_hidden:
            filters['is_hidden'] = False
        return self.find(filters=filters, order_by='order')
    
    def get_by_slug(self, playlist_id: str, slug: str) -> Optional[Group]:
        """Get group by slug."""
        results = self.find(playlist_id=playlist_id, slug=slug, limit=1)
        return results[0] if results else None
    
    def reorder(self, group_ids: List[str]) -> int:
        """Reorder groups by ID list."""
        with self._lock:
            updated = 0
            for order, group_id in enumerate(group_ids):
                group = self._data.get(group_id)
                if group:
                    group.order = order
                    group.touch()
                    updated += 1
            return updated


class EPGRepository(InMemoryRepository[EPGProgram]):
    """Repository for EPG Program entities."""
    
    def __init__(self):
        super().__init__(EPGProgram)
    
    def get_by_channel(
        self,
        channel_id: str,
        start_time: datetime = None,
        end_time: datetime = None,
        limit: int = 100
    ) -> List[EPGProgram]:
        """Get EPG programs for a channel."""
        with self._lock:
            results = []
            for program in self._data.values():
                if program.channel_id != channel_id:
                    continue
                if start_time and program.end_time < start_time:
                    continue
                if end_time and program.start_time > end_time:
                    continue
                results.append(program)
            
            results.sort(key=lambda p: p.start_time)
            return results[:limit]
    
    def get_current(self, channel_id: str) -> Optional[EPGProgram]:
        """Get currently airing program for a channel."""
        now = datetime.now(timezone.utc)
        programs = self.get_by_channel(channel_id, start_time=now, end_time=now)
        for program in programs:
            if program.start_time <= now <= program.end_time:
                return program
        return None
    
    def get_next(self, channel_id: str) -> Optional[EPGProgram]:
        """Get next upcoming program for a channel."""
        now = datetime.now(timezone.utc)
        programs = self.get_by_channel(channel_id, start_time=now, limit=2)
        for program in programs:
            if program.start_time > now:
                return program
        return None
    
    def clear_channel(self, channel_id: str) -> int:
        """Clear all EPG data for a channel."""
        with self._lock:
            to_delete = [
                id for id, p in self._data.items()
                if p.channel_id == channel_id
            ]
            for id in to_delete:
                del self._data[id]
            return len(to_delete)
    
    def clear_old(self, before: datetime = None) -> int:
        """Clear EPG data older than specified time."""
        if before is None:
            before = datetime.now(timezone.utc)
        
        with self._lock:
            to_delete = [
                id for id, p in self._data.items()
                if p.end_time < before
            ]
            for id in to_delete:
                del self._data[id]
            return len(to_delete)


class SeriesRepository(InMemoryRepository[Series]):
    """Repository for Series entities."""
    
    def __init__(self):
        super().__init__(Series)
    
    def get_by_playlist(self, playlist_id: str) -> List[Series]:
        """Get series for a playlist."""
        return self.find(playlist_id=playlist_id, order_by='name')
    
    def search(
        self,
        query: str,
        playlist_id: str = None,
        limit: int = 50
    ) -> List[Series]:
        """Search series by name."""
        query_lower = query.lower()
        
        with self._lock:
            results = []
            for series in self._data.values():
                if query_lower in series.name.lower():
                    if not playlist_id or series.playlist_id == playlist_id:
                        results.append(series)
                        if len(results) >= limit:
                            break
            return results


class StreamSourceRepository(InMemoryRepository[StreamSource]):
    """Repository for StreamSource entities."""
    
    def __init__(self):
        super().__init__(StreamSource)
    
    def get_by_channel(self, channel_id: str) -> List[StreamSource]:
        """Get sources for a channel, ordered by priority."""
        return self.find(channel_id=channel_id, order_by='priority')
    
    def get_primary(self, channel_id: str) -> Optional[StreamSource]:
        """Get primary source for a channel."""
        sources = self.find(channel_id=channel_id, is_primary=True, limit=1)
        if sources:
            return sources[0]
        # Fall back to lowest priority
        sources = self.get_by_channel(channel_id)
        return sources[0] if sources else None


# =============================================================================
# JSON File Repository
# =============================================================================

class JsonFileRepository(InMemoryRepository[T]):
    """
    Repository that persists data to JSON files.
    
    Extends InMemoryRepository to add file-based persistence.
    Data is loaded on initialization and saved after write operations.
    Writes are debounced (1 second) to batch rapid changes.
    """
    
    def __init__(self, model_class: Type[T], file_path: str):
        super().__init__(model_class)
        self._file_path = Path(file_path)
        self._save_timer: Optional[Timer] = None
        self._save_delay = 1.0  # seconds
        
        # Ensure directory exists
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        self._load()
    
    def _load(self) -> None:
        """Load data from JSON file."""
        if not self._file_path.exists():
            return
        
        try:
            with open(self._file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            for item_data in raw_data:
                try:
                    entity = self._deserialize(item_data)
                    self._data[entity.id] = entity
                except Exception as e:
                    logger.warning(f"Failed to deserialize {self._model_class.__name__}: {e}")
            
            logger.info(
                f"Loaded {len(self._data)} {self._model_class.__name__} "
                f"items from {self._file_path}"
            )
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse {self._file_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load {self._file_path}: {e}")
    
    def _deserialize(self, data: dict) -> T:
        """Deserialize a dict to a model instance."""
        # Convert datetime strings back to datetime objects
        for key, value in list(data.items()):
            if isinstance(value, str) and key in (
                'created_at', 'updated_at', 'start_time', 'end_time',
                'last_synced', 'last_watched', 'last_checked'
            ):
                try:
                    data[key] = datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    pass
            # Convert enum string values back
            elif key == 'stream_type':
                from management.models import StreamType
                try:
                    data[key] = StreamType(value)
                except (ValueError, KeyError):
                    pass
            elif key == 'status' and isinstance(value, str) and value in (
                'active', 'inactive', 'error', 'unknown'
            ):
                from management.models import StreamStatus
                try:
                    data[key] = StreamStatus(value)
                except (ValueError, KeyError):
                    pass
            elif key == 'catchup_type':
                from management.models import CatchupType
                try:
                    data[key] = CatchupType(value)
                except (ValueError, KeyError):
                    pass
            elif key == 'rating':
                from management.models import ContentRating
                try:
                    data[key] = ContentRating(value)
                except (ValueError, KeyError):
                    pass
        
        # Remove relationship fields that aren't stored
        for rel_field in ('group', 'current_program', 'sources', 'episodes', 'groups'):
            data.pop(rel_field, None)
        
        # Remove computed fields
        for computed in ('duration_formatted', 'episode_string',
                         'watch_progress_percent', 'total_items'):
            data.pop(computed, None)
        
        return self._model_class(**data)
    
    def _serialize(self, entity: T) -> dict:
        """Serialize a model instance to a JSON-safe dict."""
        data = {}
        for key, value in asdict(entity).items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, Enum):
                data[key] = value.value
            else:
                data[key] = value
        
        # Remove relationship fields
        for rel_field in ('group', 'current_program', 'sources', 'episodes', 'groups'):
            data.pop(rel_field, None)
        
        # Remove computed fields
        for computed in ('duration_formatted', 'episode_string',
                         'watch_progress_percent', 'total_items'):
            data.pop(computed, None)
        
        return data
    
    def _schedule_save(self) -> None:
        """Schedule a debounced save."""
        if self._save_timer:
            self._save_timer.cancel()
        self._save_timer = Timer(self._save_delay, self._save)
        self._save_timer.daemon = True
        self._save_timer.start()
    
    def _save(self) -> None:
        """Save all data to JSON file."""
        try:
            with self._lock:
                data = [self._serialize(entity) for entity in self._data.values()]
            
            # Write to temp file then rename for atomicity
            tmp_path = self._file_path.with_suffix('.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            tmp_path.replace(self._file_path)
            logger.debug(f"Saved {len(data)} {self._model_class.__name__} items")
        except Exception as e:
            logger.error(f"Failed to save {self._file_path}: {e}")
    
    def save_now(self) -> None:
        """Force immediate save (bypasses debounce)."""
        if self._save_timer:
            self._save_timer.cancel()
        self._save()
    
    # Override write operations to trigger save
    
    def create(self, entity: T) -> T:
        result = super().create(entity)
        self._schedule_save()
        return result
    
    def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        result = super().update(id, data)
        if result:
            self._schedule_save()
        return result
    
    def delete(self, id: str) -> bool:
        result = super().delete(id)
        if result:
            self._schedule_save()
        return result
    
    def bulk_create(self, entities: List[T]) -> List[T]:
        result = super().bulk_create(entities)
        if result:
            self._schedule_save()
        return result
    
    def bulk_delete(self, ids: List[str]) -> int:
        result = super().bulk_delete(ids)
        if result:
            self._schedule_save()
        return result
    
    def clear(self) -> int:
        result = super().clear()
        if result:
            self._schedule_save()
        return result


# =============================================================================
# Specialized JSON Repositories
# =============================================================================

class JsonPlaylistRepository(JsonFileRepository[Playlist]):
    """JSON-persisted Playlist repository."""
    def __init__(self, data_dir: str):
        super().__init__(Playlist, os.path.join(data_dir, 'playlists.json'))
    
    def get_default(self) -> Optional[Playlist]:
        results = self.find(is_default=True, limit=1)
        return results[0] if results else None
    
    def set_default(self, id: str) -> bool:
        with self._lock:
            playlist = self.get(id)
            if not playlist:
                return False
            for p in self._data.values():
                if p.is_default and p.id != id:
                    p.is_default = False
                    p.touch()
            playlist.is_default = True
            playlist.touch()
        self._schedule_save()
        return True


class JsonChannelRepository(JsonFileRepository[Channel]):
    """JSON-persisted Channel repository."""
    def __init__(self, data_dir: str):
        super().__init__(Channel, os.path.join(data_dir, 'channels.json'))
    
    def get_by_playlist(self, playlist_id, group_id=None, include_hidden=False, order_by='order'):
        filters = {'playlist_id': playlist_id}
        if group_id: filters['group_id'] = group_id
        if not include_hidden: filters['is_hidden'] = False
        return self.find(filters=filters, order_by=order_by)
    
    def get_favorites(self, playlist_id=None):
        filters = {'is_favorite': True}
        if playlist_id: filters['playlist_id'] = playlist_id
        return self.find(filters=filters)
    
    def search(self, query, playlist_id=None, limit=50):
        query_lower = query.lower()
        filters = {}
        if playlist_id: filters['playlist_id'] = playlist_id
        with self._lock:
            results = []
            for channel in self._data.values():
                if query_lower in channel.name.lower():
                    if not filters or self._matches_filters(channel, filters):
                        results.append(channel)
                        if len(results) >= limit: break
            return results
    
    def reorder(self, channel_ids):
        with self._lock:
            updated = 0
            for order, cid in enumerate(channel_ids):
                channel = self._data.get(cid)
                if channel:
                    channel.order = order
                    channel.touch()
                    updated += 1
        if updated: self._schedule_save()
        return updated


class JsonVODRepository(JsonFileRepository[VOD]):
    """JSON-persisted VOD repository."""
    def __init__(self, data_dir: str):
        super().__init__(VOD, os.path.join(data_dir, 'vod.json'))
    
    def get_by_playlist(self, playlist_id, group_id=None, content_type=None, include_hidden=False):
        filters = {'playlist_id': playlist_id}
        if group_id: filters['group_id'] = group_id
        if content_type: filters['content_type'] = content_type
        if not include_hidden: filters['is_hidden'] = False
        return self.find(filters=filters, order_by='name')
    
    def get_series_episodes(self, series_id, season=None):
        filters = {'series_id': series_id}
        if season: filters['season'] = season
        return self.find(filters=filters, order_by='episode')
    
    def get_recently_watched(self, playlist_id=None, limit=20):
        results = self.find(
            filters={'playlist_id': playlist_id} if playlist_id else None,
            order_by='last_watched', order_desc=True, limit=limit * 2
        )
        return [v for v in results if v.watch_position > 0 or v.last_watched][:limit]
    
    def get_continue_watching(self, playlist_id=None, limit=20):
        results = self.find(
            filters={'playlist_id': playlist_id} if playlist_id else None,
            order_by='last_watched', order_desc=True
        )
        return [
            v for v in results
            if v.watch_position > 0 and not v.watch_completed and v.watch_progress_percent < 95
        ][:limit]
    
    def search(self, query, playlist_id=None, content_type=None, limit=50):
        query_lower = query.lower()
        filters = {}
        if playlist_id: filters['playlist_id'] = playlist_id
        if content_type: filters['content_type'] = content_type
        with self._lock:
            results = []
            for vod in self._data.values():
                if query_lower in vod.name.lower() or (vod.plot and query_lower in vod.plot.lower()):
                    if not filters or self._matches_filters(vod, filters):
                        results.append(vod)
                        if len(results) >= limit: break
            return results


class JsonGroupRepository(JsonFileRepository[Group]):
    """JSON-persisted Group repository."""
    def __init__(self, data_dir: str):
        super().__init__(Group, os.path.join(data_dir, 'groups.json'))
    
    def get_by_playlist(self, playlist_id, include_hidden=False):
        filters = {'playlist_id': playlist_id}
        if not include_hidden: filters['is_hidden'] = False
        return self.find(filters=filters, order_by='order')
    
    def get_by_slug(self, playlist_id, slug):
        results = self.find(playlist_id=playlist_id, slug=slug, limit=1)
        return results[0] if results else None
    
    def reorder(self, group_ids):
        with self._lock:
            updated = 0
            for order, gid in enumerate(group_ids):
                group = self._data.get(gid)
                if group:
                    group.order = order
                    group.touch()
                    updated += 1
        if updated: self._schedule_save()
        return updated


class JsonEPGRepository(JsonFileRepository[EPGProgram]):
    """JSON-persisted EPG repository."""
    def __init__(self, data_dir: str):
        super().__init__(EPGProgram, os.path.join(data_dir, 'epg.json'))
    
    def get_by_channel(self, channel_id, start_time=None, end_time=None, limit=100):
        with self._lock:
            results = []
            for program in self._data.values():
                if program.channel_id != channel_id: continue
                if start_time and program.end_time < start_time: continue
                if end_time and program.start_time > end_time: continue
                results.append(program)
            results.sort(key=lambda p: p.start_time)
            return results[:limit]
    
    def get_current(self, channel_id):
        now = datetime.now(timezone.utc)
        programs = self.get_by_channel(channel_id, start_time=now, end_time=now)
        for program in programs:
            if program.start_time <= now <= program.end_time:
                return program
        return None
    
    def get_next(self, channel_id):
        now = datetime.now(timezone.utc)
        programs = self.get_by_channel(channel_id, start_time=now, limit=2)
        for program in programs:
            if program.start_time > now:
                return program
        return None
    
    def clear_channel(self, channel_id):
        with self._lock:
            to_delete = [id for id, p in self._data.items() if p.channel_id == channel_id]
            for id in to_delete: del self._data[id]
        if to_delete: self._schedule_save()
        return len(to_delete)
    
    def clear_old(self, before=None):
        if before is None:
            before = datetime.now(timezone.utc)
        with self._lock:
            to_delete = [id for id, p in self._data.items() if p.end_time < before]
            for id in to_delete: del self._data[id]
        if to_delete: self._schedule_save()
        return len(to_delete)


class JsonSeriesRepository(JsonFileRepository[Series]):
    """JSON-persisted Series repository."""
    def __init__(self, data_dir: str):
        super().__init__(Series, os.path.join(data_dir, 'series.json'))
    
    def get_by_playlist(self, playlist_id):
        return self.find(playlist_id=playlist_id, order_by='name')
    
    def search(self, query, playlist_id=None, limit=50):
        query_lower = query.lower()
        with self._lock:
            results = []
            for series in self._data.values():
                if query_lower in series.name.lower():
                    if not playlist_id or series.playlist_id == playlist_id:
                        results.append(series)
                        if len(results) >= limit: break
            return results


class JsonStreamSourceRepository(JsonFileRepository[StreamSource]):
    """JSON-persisted StreamSource repository."""
    def __init__(self, data_dir: str):
        super().__init__(StreamSource, os.path.join(data_dir, 'sources.json'))
    
    def get_by_channel(self, channel_id):
        return self.find(channel_id=channel_id, order_by='priority')
    
    def get_primary(self, channel_id):
        sources = self.find(channel_id=channel_id, is_primary=True, limit=1)
        if sources: return sources[0]
        sources = self.get_by_channel(channel_id)
        return sources[0] if sources else None


# =============================================================================
# Storage Manager
# =============================================================================

class Storage:
    """
    Central storage manager providing access to all repositories.
    
    Automatically selects the appropriate backend based on configuration:
    - 'memory': Fast in-memory only (data lost on restart)
    - 'json': JSON file persistence (survives restarts)
    
    Usage:
        storage = Storage()
        playlist = storage.playlists.create(Playlist(name="My Playlist"))
        channel = storage.channels.create(Channel(name="CNN", playlist_id=playlist.id))
    """
    
    def __init__(self):
        from management.config import config
        
        backend = config.storage.backend
        
        if backend == 'json':
            data_dir = config.storage.data_dir
            logger.info(f"Using JSON file storage in: {data_dir}")
            
            self.playlists = JsonPlaylistRepository(data_dir)
            self.channels = JsonChannelRepository(data_dir)
            self.vod = JsonVODRepository(data_dir)
            self.groups = JsonGroupRepository(data_dir)
            self.epg = JsonEPGRepository(data_dir)
            self.series = JsonSeriesRepository(data_dir)
            self.sources = JsonStreamSourceRepository(data_dir)
        else:
            logger.info("Using in-memory storage (data will not persist)")
            
            self.playlists = PlaylistRepository()
            self.channels = ChannelRepository()
            self.vod = VODRepository()
            self.groups = GroupRepository()
            self.epg = EPGRepository()
            self.series = SeriesRepository()
            self.sources = StreamSourceRepository()
    
    def clear_all(self) -> Dict[str, int]:
        """Clear all data from all repositories."""
        return {
            'playlists': self.playlists.clear(),
            'channels': self.channels.clear(),
            'vod': self.vod.clear(),
            'groups': self.groups.clear(),
            'epg': self.epg.clear(),
            'series': self.series.clear(),
            'sources': self.sources.clear(),
        }
    
    def get_stats(self) -> Dict[str, int]:
        """Get counts from all repositories."""
        return {
            'playlists': self.playlists.count(),
            'channels': self.channels.count(),
            'vod': self.vod.count(),
            'groups': self.groups.count(),
            'epg': self.epg.count(),
            'series': self.series.count(),
            'sources': self.sources.count(),
        }
    
    def save_all(self) -> None:
        """Force save all repositories (JSON backend only)."""
        for repo_name in ('playlists', 'channels', 'vod', 'groups', 'epg', 'series', 'sources'):
            repo = getattr(self, repo_name)
            if hasattr(repo, 'save_now'):
                repo.save_now()


# Global storage instance
storage = Storage()