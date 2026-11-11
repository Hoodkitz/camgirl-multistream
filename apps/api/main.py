"""Multi-Stream & Chat-Aggregation – API."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.routers import automation, chat, credentials, stats, streams, system, tenants
from apps.core.config import settings
from apps.db.session import init_models
from apps.domain.ratelimit import TokenBucket

VERSION = "0.2.0"
limiter = TokenBucket(capacity=settings.RATE_LIMIT_PER_MINUTE, refill_per_sec=settings.RATE_LIMIT_PER_MINUTE / 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.AUTO_CREATE_TABLES:
        await init_models()
    yield


app = FastAPI(title="Multi-Stream & Chat-Aggregation", version=VERSION, lifespan=lifespan,
              docs_url="/docs" if settings.dev_endpoints_enabled else None)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def rate_limit_and_headers(request: Request, call_next):
    # Interaktive Nutzer-Routen: 60/min pro Token (Spec 10.1). Maschinen-Routen haben eigene Limits.
    auth = request.headers.get("authorization")
    if auth and request.url.path.startswith("/api/"):
        ok, retry = limiter.take(auth[-32:])
        if not ok:
            return JSONResponse({"detail": "Zu viele Anfragen"}, status_code=429,
                                headers={"Retry-After": str(max(1, int(retry + 0.999)))})
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


for r in (tenants, credentials, streams, chat, automation, stats, system):
    app.include_router(r.router)
if settings.dev_endpoints_enabled:
    from apps.api.routers import dev
    app.include_router(dev.router)


@app.get("/healthz")
async def health():
    return {"status": "ok", "version": VERSION}
