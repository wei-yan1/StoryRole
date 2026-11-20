"""Image upload API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.v1.auth import current_user
from app.schemas.auth import UserOut
from app.services import oss_storage


router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    """上传一张图片到 OSS，返回可直接使用的 URL。

    注册方式见 docs/OSS图片存储接入指南.md：在 app/main.py 里
    include_router(uploads_router) 即可。
    """
    data = await file.read()
    try:
        return oss_storage.upload_image(
            data,
            file.filename or "image",
            content_type=file.content_type,
            scope=f"users/{user.id}",
        )
    except oss_storage.OSSStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/images")
def list_images(
    prefix: str | None = None,
    limit: int = 100,
    user: UserOut = Depends(current_user),
) -> dict[str, object]:
    """列出指定前缀下的图片，默认 images/。"""
    del user  # 仅用于鉴权
    try:
        return {"items": oss_storage.list_images(prefix=prefix, limit=limit)}
    except oss_storage.OSSStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
