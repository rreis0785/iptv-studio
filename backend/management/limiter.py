"""
Rate-limiter singleton for the management API.

Initialised without an app here so it can be imported by Blueprint modules.
Call ``limiter.init_app(app)`` inside the application factory.

Default limits (applied to every endpoint unless overridden):
  - 200 requests per hour per IP
  - 50 requests per minute per IP

Write-heavy operations (import, bulk-create) have tighter per-route limits
applied via ``@limiter.limit`` decorators in their respective route files.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",
)
