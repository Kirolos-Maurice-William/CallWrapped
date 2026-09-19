from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db
from app.routers import calls, audio_stream, dashboard, sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ai_third_participant")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down AI Third Participant backend.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for development & local IP testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(calls.router)
app.include_router(audio_stream.router)
app.include_router(dashboard.router)
app.include_router(sync.router)

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "assemblyai_model": settings.ASSEMBLYAI_MODEL
    }

# Mount Next.js static export directly so whole app runs on single port
import os
from fastapi.staticfiles import StaticFiles

frontend_out = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../frontend/out"))
if os.path.exists(frontend_out):
    app.mount("/", StaticFiles(directory=frontend_out, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
