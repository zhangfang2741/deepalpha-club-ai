"""通用媒体文件上传与读取接口."""

import mimetypes
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.v1.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.models.user import User

router = APIRouter()


def _storage_dir() -> Path:
    path = Path(settings.MEDIA_STORAGE_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.post("/upload")
@limiter.limit("20 per minute")
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict[str, str | int]:
    """上传一个媒体文件并返回可供外部读取的 URL."""
    suffix = Path(file.filename or "").suffix.lower()
    guessed_type = mimetypes.guess_type(file.filename or "")[0]
    content_type = file.content_type or guessed_type
    if content_type == "application/octet-stream" and guessed_type:
        content_type = guessed_type
    if content_type not in settings.MEDIA_ALLOWED_TYPES and guessed_type not in settings.MEDIA_ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="不支持的媒体类型")
    content_type = guessed_type or content_type or "application/octet-stream"

    media_id = f"{uuid4().hex}{secrets.token_hex(4)}{suffix}"
    destination = _storage_dir() / media_id
    size = 0
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MEDIA_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="文件超过大小限制")
                output.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        destination.unlink(missing_ok=True)
        logger.exception("media_upload_failed", error=str(exc), user_id=user.id)
        raise HTTPException(status_code=500, detail="文件保存失败") from exc
    finally:
        await file.close()

    logger.info("media_uploaded", media_id=media_id, size_bytes=size, user_id=user.id)
    return {
        "id": media_id,
        "url": f"{settings.PUBLIC_BASE_URL}{settings.API_V1_STR}/media/files/{media_id}",
        "content_type": content_type,
        "size_bytes": size,
    }


@router.api_route("/files/{media_id}", methods=["GET", "HEAD"])
@limiter.limit("120 per minute")
async def read_media(request: Request, media_id: str) -> FileResponse:
    """读取已上传媒体，供 Buffer 等外部服务抓取."""
    if Path(media_id).name != media_id or "/" in media_id or "\\" in media_id:
        raise HTTPException(status_code=400, detail="文件标识无效")
    path = _storage_dir() / media_id
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=content_type, filename=path.name)
