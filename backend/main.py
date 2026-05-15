import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.logger import get_logger
from routers import batch, demo, stream, workers

logger = get_logger(__name__)

# Directories must exist before StaticFiles is instantiated at import time.
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.OUTPUT_DIR, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("API starting up")
    yield
    logger.info("API shutting down")


app = FastAPI(
    title="Distributed Image Processing Pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(batch.router, prefix="/api")
app.include_router(workers.router, prefix="/api")
app.include_router(stream.router, prefix="/api")
app.include_router(demo.router, prefix="/api")

# Static file mounts — served after all API routes.
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")
