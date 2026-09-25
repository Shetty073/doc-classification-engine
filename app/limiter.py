from slowapi import Limiter
from slowapi.util import get_remote_address
from app.config import settings

# Global SlowAPI limiter configured with client IP keying
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
)
