import os
import sys
from pathlib import Path
import logging
from contextlib import asynccontextmanager

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routes import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("callwrapped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down CallWrapped backend.")


app = FastAPI(
    title="CallWrapped API",
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS configuration
cors_origins = (
    [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
    if isinstance(settings.CORS_ORIGINS, str)
    else settings.CORS_ORIGINS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "CallWrapped",
        "version": settings.VERSION,
        "assemblyai_model": settings.ASSEMBLYAI_MODEL
    }


# Mount recordings directory for audio evidence playback
recordings_dir = Path(__file__).resolve().parent.parent.parent / "recordings"
if recordings_dir.exists():
    app.mount("/recordings", StaticFiles(directory=str(recordings_dir)), name="recordings")

# Mount Next.js static export directly so whole app runs on single port (8000)
frontend_out = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/out"))
if os.path.exists(frontend_out):
    app.mount("/", StaticFiles(directory=frontend_out, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
