import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audit, documents, extraction, health, upload
from app.config import ensure_data_dirs
from app.db.models import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

ensure_data_dirs()
init_db()

app = FastAPI(title="AuditTrace", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(extraction.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
