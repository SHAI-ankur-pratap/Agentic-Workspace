import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from database import Base, engine
from routers import auth, projects, testcases, executions, reports, ai, webhooks

# Structured JSON logging
logging.basicConfig(
    format='{"ts":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
    level=logging.INFO,
)
logger = logging.getLogger("tcms")

# Rate limiter (shared with auth router)
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="TCMS — AI-Native Test Case Management", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables
Base.metadata.create_all(bind=engine)

# Routers — each router defines its own full prefix; main.py only adds auth prefix
# (auth router was stripped of its prefix to allow main.py to set it)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
# These routers carry their own /api/... prefix already
app.include_router(projects.router)
app.include_router(testcases.router)
app.include_router(executions.router)
app.include_router(reports.router)
app.include_router(ai.router)
app.include_router(webhooks.router)

# Public report route (no /api prefix)
app.include_router(reports.public_router, tags=["public-reports"])

# MCP server
try:
    from mcp_server import mcp
    app.mount("/mcp", mcp.get_asgi_app())
    logger.info("MCP server mounted at /mcp")
except Exception as e:
    logger.warning(f"MCP server not mounted: {e}")

# Startup: seed templates + start scheduler
@app.on_event("startup")
async def startup():
    try:
        from seed_templates import seed_templates
        seed_templates()
    except Exception as e:
        logger.warning(f"Template seeding skipped: {e}")
    try:
        from digest import start_scheduler
        start_scheduler()
        logger.info("Digest scheduler started")
    except Exception as e:
        logger.warning(f"Digest scheduler not started: {e}")


@app.on_event("shutdown")
async def shutdown():
    try:
        from digest import stop_scheduler
        stop_scheduler()
    except Exception:
        pass


@app.get("/health")
async def health():
    return {"status": "ok", "service": "tcms"}
