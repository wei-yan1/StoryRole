"""阿里云 OSS 图片上传与读取封装。

项目已依赖 alibabacloud-oss-v2（见 pyproject.toml），这里只处理图片对象，
上传、生成访问链接、读取、删除、列举都走同一个 Bucket。

环境变量见 .env.example 的 OSS_* 段；未配置 AccessKey 时不会影响应用启动，
只有真正调用上传/读取接口才会抛 OSSStorageError。
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)

DEFAULT_REGION = "cn-guangzhou"
DEFAULT_ENDPOINT = "https://oss-cn-guangzhou.aliyuncs.com"
DEFAULT_BUCKET = "lbwnb111"
DEFAULT_PUBLIC_BASE_URL = "https://lbwnb111.oss-cn-guangzhou.aliyuncs.com"

IMAGE_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
DEFAULT_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class OSSStorageError(RuntimeError):
    """OSS 配置缺失或调用失败时抛出。"""


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _settings() -> dict[str, str]:
    return {
        "region": _env("OSS_REGION", DEFAULT_REGION),
        "endpoint": _env("OSS_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/"),
        "bucket": _env("OSS_BUCKET", DEFAULT_BUCKET),
        "access_key_id": _env("OSS_ACCESS_KEY_ID"),
        "access_key_secret": _env("OSS_ACCESS_KEY_SECRET"),
        "public_base_url": _env("OSS_PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).rstrip("/"),
        "image_prefix": _env("OSS_IMAGE_PREFIX", "images").strip("/"),
    }


def max_image_bytes() -> int:
    raw = _env("OSS_MAX_IMAGE_BYTES")
    return int(raw) if raw.isdigit() else DEFAULT_MAX_IMAGE_BYTES


def is_configured() -> bool:
    """AccessKey 与 Bucket 是否齐全；前端可据此决定是否显示上传入口。"""
    cfg = _settings()
    return bool(cfg["access_key_id"] and cfg["access_key_secret"] and cfg["bucket"])


def _client() -> tuple[Any, Any]:
    """按需导入 SDK 并创建客户端，避免未配置时拖垮应用启动。"""
    import alibabacloud_oss_v2 as oss

    cfg = _settings()
    if not cfg["access_key_id"] or not cfg["access_key_secret"]:
        raise OSSStorageError(
            "缺少 OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET，请在 .env 中配置后重启服务"
        )
    config = oss.config.Config(
        region=cfg["region"],
        endpoint=cfg["endpoint"],
        credentials_provider=oss.credentials.StaticCredentialsProvider(
            cfg["access_key_id"],
            cfg["access_key_secret"],
        ),
    )
    return oss, oss.Client(config)


def build_object_key(
    filename: str,
    category: str | None = None,
    scope: str | None = None,
) -> str:
    """生成对象键，例如 images/2026/11/users/1/<uuid>.jpg。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_CONTENT_TYPES:
        raise OSSStorageError(f"不支持的图片格式: {suffix or '无扩展名'}")

    cfg = _settings()
    segments: list[str] = []
    base = (category if category is not None else cfg["image_prefix"]).strip("/")
    if base:
        segments.append(base)
    segments.append(datetime.now().strftime("%Y/%m"))
    if scope:
        segments.append(scope.strip("/"))
    segments.append(f"{uuid.uuid4().hex}{suffix}")
    return "/".join(segments)


def public_url(key: str) -> str:
    """拼接公网访问地址；Bucket 为公共读时可直接使用。"""
    cfg = _settings()
    return f"{cfg['public_base_url']}/{quote(key.lstrip('/'), safe='/')}"


def upload_image(
    data: bytes,
    filename: str,
    content_type: str | None = None,
    category: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """上传图片字节，返回对象键、公网 URL、大小和内容类型。"""
    if not data:
        raise OSSStorageError("图片内容为空")
    if len(data) > max_image_bytes():
        raise OSSStorageError(f"图片超过大小上限 {max_image_bytes()} 字节")

    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_CONTENT_TYPES:
        raise OSSStorageError(f"不支持的图片格式: {suffix or '无扩展名'}")

    key = build_object_key(filename, category=category, scope=scope)
    resolved_type = content_type or IMAGE_CONTENT_TYPES[suffix]

    oss, client = _client()
    cfg = _settings()
    try:
        client.put_object(
            oss.PutObjectRequest(
                bucket=cfg["bucket"],
                key=key,
                body=data,
                content_type=resolved_type,
            )
        )
    except Exception as exc:  # noqa: BLE001 - 统一转成项目内异常
        raise OSSStorageError(f"上传失败: {exc}") from exc

    return {
        "bucket": cfg["bucket"],
        "key": key,
        "url": public_url(key),
        "size": len(data),
        "content_type": resolved_type,
    }


def upload_image_file(
    file_path: str | Path,
    category: str | None = None,
    scope: str | None = None,
) -> dict[str, Any]:
    """上传本地图片文件。"""
    path = Path(file_path)
    if not path.is_file():
        raise OSSStorageError(f"文件不存在: {path}")
    return upload_image(
        path.read_bytes(),
        path.name,
        category=category,
        scope=scope,
    )


def read_image_bytes(key: str) -> bytes:
    """按对象键读取图片内容，用于需要二次处理的场景。"""
    oss, client = _client()
    cfg = _settings()
    try:
        result = client.get_object(
            oss.GetObjectRequest(bucket=cfg["bucket"], key=key.lstrip("/"))
        )
    except Exception as exc:  # noqa: BLE001
        raise OSSStorageError(f"读取失败: {exc}") from exc

    body = result.body
    if body is None:
        raise OSSStorageError("对象内容为空")
    try:
        return body.read()
    finally:
        close = getattr(body, "close", None)
        if callable(close):
            close()


def signed_url(key: str, expires_seconds: int = 3600) -> str:
    """生成临时签名链接；Bucket 改成私有读之后靠它访问。"""
    oss, client = _client()
    cfg = _settings()
    result = client.presign(
        oss.GetObjectRequest(bucket=cfg["bucket"], key=key.lstrip("/")),
        expires=timedelta(seconds=expires_seconds),
    )
    return result.url


def delete_image(key: str) -> None:
    """删除单个对象。"""
    oss, client = _client()
    cfg = _settings()
    try:
        client.delete_object(
            oss.DeleteObjectRequest(bucket=cfg["bucket"], key=key.lstrip("/"))
        )
    except Exception as exc:  # noqa: BLE001
        raise OSSStorageError(f"删除失败: {exc}") from exc


def list_images(prefix: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """列举图片对象，默认列 images/ 前缀。"""
    oss, client = _client()
    cfg = _settings()
    base = (prefix if prefix is not None else cfg["image_prefix"]).strip("/")
    request_prefix = f"{base}/" if base else ""
    try:
        result = client.list_objects_v2(
            oss.ListObjectsV2Request(
                bucket=cfg["bucket"],
                prefix=request_prefix,
                max_keys=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise OSSStorageError(f"列举失败: {exc}") from exc

    items: list[dict[str, Any]] = []
    for obj in result.contents or []:
        items.append(
            {
                "key": obj.key,
                "size": obj.size,
                "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                "url": public_url(obj.key or ""),
            }
        )
    return items


def image_process_url(
    url: str,
    width: int | None = None,
    quality: int | None = 80,
    fmt: str | None = "webp",
) -> str:
    """在 URL 后追加 OSS 图片处理参数，例如缩放到 800px、质量 80、转 WebP。"""
    actions: list[str] = []
    if width:
        actions.append(f"resize,w_{width}")
    if quality:
        actions.append(f"quality,q_{quality}")
    if fmt:
        actions.append(f"format,{fmt}")
    if not actions:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}x-oss-process=image/{'/'.join(actions)}"
