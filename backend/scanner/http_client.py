"""
Async HTTP client for the media scanner.

Provides a unified interface for making HTTP requests with:
- Automatic retries
- Rate limiting
- User agent rotation
- Proxy support
- Response caching
"""

import asyncio
import logging
import itertools
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class HttpResponse:
    """HTTP response wrapper."""
    
    url: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    text: str = ""
    content: bytes = b""
    
    @property
    def success(self) -> bool:
        """Check if request was successful."""
        return 200 <= self.status_code < 400
    
    @property
    def is_redirect(self) -> bool:
        """Check if response is a redirect."""
        return 300 <= self.status_code < 400
    
    def json(self) -> Any:
        """Parse response as JSON."""
        import json
        return json.loads(self.text)


class HttpClient:
    """
    Async HTTP client with advanced features.
    
    Features:
    - Automatic retries with exponential backoff
    - Rate limiting per domain
    - User agent rotation
    - Response caching
    - Cookie persistence
    """
    
    DEFAULT_USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]
    
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        requests_per_second: float = 2.0,
        requests_per_second: float = 2.0,
        user_agents: List[str] = None,
        proxies: List[str] = None,
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.requests_per_second = requests_per_second
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS
        
        # Proxy rotation
        from scanner.config import config
        self.proxies = proxies or config.network.proxies
        self._proxy_cycle = itertools.cycle(self.proxies) if self.proxies else None
        
        # Rate limiting
        self._last_request_time: Dict[str, float] = {}
        self._rate_lock = asyncio.Lock()
        
        # Session (lazy init)
        self._session = None
    
    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None:
            try:
                import aiohttp
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                self._session = aiohttp.Session(timeout=timeout)
            except ImportError:
                # Fall back to synchronous requests
                pass
        return self._session
    
    async def _rate_limit(self, domain: str) -> None:
        """Apply rate limiting for domain."""
        async with self._rate_lock:
            now = time.time()
            min_interval = 1.0 / self.requests_per_second
            
            if domain in self._last_request_time:
                elapsed = now - self._last_request_time[domain]
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
            
            self._last_request_time[domain] = time.time()
    
    def _get_headers(self, headers: Dict[str, str] = None) -> Dict[str, str]:
        """Build request headers."""
        default_headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        if headers:
            default_headers.update(headers)
        
        return default_headers
    
    def _get_proxy(self) -> Optional[str]:
        """Get next proxy from pool."""
        if self._proxy_cycle:
            return next(self._proxy_cycle)
        return None
    
    async def get(
        self,
        url: str,
        headers: Dict[str, str] = None,
        params: Dict[str, str] = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """Make GET request."""
        return await self._request(
            'GET', url,
            headers=headers,
            params=params,
            allow_redirects=allow_redirects
        )
    
    async def post(
        self,
        url: str,
        headers: Dict[str, str] = None,
        data: Any = None,
        json: Any = None,
    ) -> HttpResponse:
        """Make POST request."""
        return await self._request(
            'POST', url,
            headers=headers,
            data=data,
            json_data=json
        )
    
    async def _request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str] = None,
        params: Dict[str, str] = None,
        data: Any = None,
        json_data: Any = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """Make HTTP request with retries."""
        parsed = urlparse(url)
        domain = parsed.netloc
        
        # Apply rate limiting
        await self._rate_limit(domain)
        
        # Build headers
        request_headers = self._get_headers(headers)
        
        # Try with aiohttp first, fall back to urllib
        for attempt in range(self.max_retries):
            try:
                response = await self._do_request(
                    method, url,
                    headers=request_headers,
                    params=params,
                    data=data,
                    json_data=json_data,
                    allow_redirects=allow_redirects
                )
                
                if response.success or response.status_code == 404:
                    return response
                
                # Retry on server errors
                if response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        logger.debug(f"Retrying {url} after {delay}s (status {response.status_code})")
                        await asyncio.sleep(delay)
                        continue
                
                return response
                
            except Exception as e:
                logger.warning(f"Request failed: {url} - {e}")
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    return HttpResponse(url=url, status_code=0, text=str(e))
        
        return HttpResponse(url=url, status_code=0, text="Max retries exceeded")
    
    async def _do_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Dict[str, str] = None,
        data: Any = None,
        json_data: Any = None,
        allow_redirects: bool = True,
    ) -> HttpResponse:
        """Perform the actual HTTP request."""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                kwargs = {
                    'headers': headers,
                    'allow_redirects': allow_redirects,
                    'timeout': aiohttp.ClientTimeout(total=self.timeout),
                }
                
                if params:
                    kwargs['params'] = params
                if data:
                    kwargs['data'] = data
                if json_data:
                    kwargs['json'] = json_data
                if json_data:
                    kwargs['json'] = json_data
                
                # Get proxy for this request
                proxy = self._get_proxy()
                if proxy:
                    kwargs['proxy'] = proxy
                
                async with session.request(method, url, **kwargs) as resp:
                    text = await resp.text()
                    content = await resp.read()
                    
                    return HttpResponse(
                        url=str(resp.url),
                        status_code=resp.status,
                        headers=dict(resp.headers),
                        text=text,
                        content=content,
                    )
                    
        except ImportError:
            # Fall back to urllib (synchronous)
            return await self._urllib_request(
                method, url, headers, params, data, json_data
            )
    
    async def _urllib_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        params: Dict[str, str] = None,
        data: Any = None,
        json_data: Any = None,
    ) -> HttpResponse:
        """Fallback using urllib (synchronous)."""
        import urllib.request
        import urllib.parse
        import json as json_lib
        
        # Build URL with params
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        
        # Prepare data
        request_data = None
        if json_data:
            request_data = json_lib.dumps(json_data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        elif data:
            if isinstance(data, dict):
                request_data = urllib.parse.urlencode(data).encode('utf-8')
            else:
                request_data = data.encode('utf-8') if isinstance(data, str) else data
        
        # Create request
        req = urllib.request.Request(url, data=request_data, headers=headers, method=method)
        
        try:
            # Run in thread pool to not block
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=self.timeout)
            )
            
            content = response.read()
            
            # Try to decode text
            encoding = response.headers.get_content_charset() or 'utf-8'
            try:
                text = content.decode(encoding)
            except UnicodeDecodeError:
                text = content.decode('utf-8', errors='replace')
            
            return HttpResponse(
                url=response.url,
                status_code=response.status,
                headers=dict(response.headers),
                text=text,
                content=content,
            )
            
        except urllib.request.HTTPError as e:
            content = e.read() if hasattr(e, 'read') else b''
            return HttpResponse(
                url=url,
                status_code=e.code,
                headers=dict(e.headers) if hasattr(e, 'headers') else {},
                text=content.decode('utf-8', errors='replace'),
                content=content,
            )
        except Exception as e:
            return HttpResponse(url=url, status_code=0, text=str(e))
    
    async def close(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()
            self._session = None


# Global client instance
http_client = HttpClient()