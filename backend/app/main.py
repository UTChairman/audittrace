from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import audit, documents, extraction, health, review, upload
from app.config import ensure_data_dirs
from app.db.models import init_db
from app.logging_config import configure_logging

configure_logging()

ensure_data_dirs()
init_db()

app = FastAPI(title="AuditTrace", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(extraction.router, prefix="/api")
app.include_router(extraction.pending_router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(review.router, prefix="/api")
