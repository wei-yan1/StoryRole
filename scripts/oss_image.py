"""OSS 图片命令行工具：上传、列举、取链接、下载。

用法（在项目根目录执行）：
  uv run python scripts/oss_image.py upload photo.jpg
  uv run python scripts/oss_image.py upload photo.jpg --scope users/1
  uv run python scripts/oss_image.py list --prefix images --limit 20
  uv run python scripts/oss_image.py url images/2026/11/xxx.jpg
  uv run python scripts/oss_image.py url images/2026/11/xxx.jpg --signed
  uv run python scripts/oss_image.py download images/2026/11/xxx.jpg ./out.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from app.services import oss_storage  # noqa: E402


def _cmd_upload(args: argparse.Namespace) -> int:
    result = oss_storage.upload_image_file(
        args.file,
        category=args.category,
        scope=args.scope,
    )
    print(result["url"])
    print(f"key={result['key']} size={result['size']} type={result['content_type']}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    items = oss_storage.list_images(prefix=args.prefix, limit=args.limit)
    if not items:
        print("（无对象）")
        return 0
    for item in items:
        size_kb = (item["size"] or 0) / 1024
        print(f"{item['key']}\t{size_kb:.1f}KB\t{item['url']}")
    return 0


def _cmd_url(args: argparse.Namespace) -> int:
    if args.signed:
        url = oss_storage.signed_url(args.key, expires_seconds=args.expires)
    else:
        url = oss_storage.public_url(args.key)
    if args.width:
        url = oss_storage.image_process_url(url, width=args.width)
    print(url)
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    data = oss_storage.read_image_bytes(args.key)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"saved {out} ({len(data)} bytes)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OSS 图片工具")
    sub = parser.add_subparsers(dest="command", required=True)

    upload = sub.add_parser("upload", help="上传本地图片")
    upload.add_argument("file")
    upload.add_argument("--category", default=None, help="一级目录，默认 images")
    upload.add_argument("--scope", default=None, help="二级目录，例如 users/1")
    upload.set_defaults(handler=_cmd_upload)

    listing = sub.add_parser("list", help="列举图片")
    listing.add_argument("--prefix", default=None)
    listing.add_argument("--limit", type=int, default=100)
    listing.set_defaults(handler=_cmd_list)

    url = sub.add_parser("url", help="输出访问链接")
    url.add_argument("key")
    url.add_argument("--signed", action="store_true", help="生成临时签名链接")
    url.add_argument("--expires", type=int, default=3600, help="签名有效期（秒）")
    url.add_argument("--width", type=int, default=None, help="附加缩放宽度")
    url.set_defaults(handler=_cmd_url)

    download = sub.add_parser("download", help="下载对象到本地")
    download.add_argument("key")
    download.add_argument("out")
    download.set_defaults(handler=_cmd_download)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except oss_storage.OSSStorageError as exc:
        print(f"[OSS] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
