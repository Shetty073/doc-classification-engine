import logging
from contextlib import asynccontextmanager
from arq.connections import RedisSettings, create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import async_engine, init_db
from app.limiter import limiter
from app.middleware import SecurityHeadersMiddleware
from app.routers import auth, documents

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager:
    - Prepares DB schema if running standalone
    - Creates shared ARQ Redis connection pool
    - Performs graceful cleanup on server shutdown
    """
    logger.info("Starting up %s...", settings.APP_NAME)

    # 1. Initialize DB tables
    try:
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)

    # 2. Initialize ARQ Redis connection pool for enqueuing async worker tasks
    try:
        redis_settings = RedisSettings(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            database=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
        )
        app.state.arq_redis = await create_pool(redis_settings)
        logger.info("ARQ Redis pool established on %s:%s", settings.REDIS_HOST, settings.REDIS_PORT)
    except Exception as e:
        logger.warning("Could not establish ARQ Redis pool on startup: %s. Worker dispatch may fail if Redis is down.", e)
        app.state.arq_redis = None

    yield

    # Shutdown logic
    logger.info("Shutting down %s...", settings.APP_NAME)
    if getattr(app.state, "arq_redis", None):
        await app.state.arq_redis.close()
        logger.info("ARQ Redis pool closed.")

    await async_engine.dispose()
    logger.info("Database engine connections closed.")


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "Enterprise-grade, asynchronous AI document classification engine for Indian banking institutions. "
        "Classifies RBI Officially Valid Documents (OVDs) for KYC and corporate lending documents (GST, ITR, PO, Invoices)."
    ),
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG or settings.APP_ENV != "production" else None,
    redoc_url="/redoc" if settings.DEBUG or settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

# ---------------------------------------------------------
# Security Middlewares (Strict Order of Execution)
# ---------------------------------------------------------

# 1. Custom Strict Security Headers (HSTS, CSP, X-Frame-Options, X-Content-Type-Options)
app.add_middleware(SecurityHeadersMiddleware)

# 2. Host Header Validation (Prevents Host header injection & DNS rebinding)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)

# 3. CORS: Strictly restricted to enterprise origins (no wildcard '*')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    max_age=3600,
)

# 4. Rate Limiter state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------
# Routers Registration
# ---------------------------------------------------------
# Mount authentication endpoints directly at root for standard /token access
app.include_router(auth.router)
# Mount document processing endpoints
app.include_router(documents.router)


@app.get("/health", tags=["Health"], summary="Service Health Check")
async def health_check():
    """Liveness and readiness check for container orchestrators."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
    }
