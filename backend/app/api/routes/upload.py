from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ocr import UploadResponse
from app.services.upload import handle_uploads

router = APIRouter(tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    return await handle_uploads(db, background_tasks, files)
