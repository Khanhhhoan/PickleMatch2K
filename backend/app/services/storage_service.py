import hashlib
import io
import logging
import os
import re
import time
import uuid
from typing import Optional

from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger("pickleball.storage")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
VENUE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "venues")
os.makedirs(VENUE_UPLOAD_DIR, exist_ok=True)

LOCAL_URL_PREFIX = "/uploads/venues/"

# Chỉ nhận ảnh bitmap. SVG bị loại vì có thể chứa mã script và được phục vụ cùng origin với API.
_PIL_FORMAT_TO_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}


def max_image_bytes() -> int:
    return settings.MAX_IMAGE_SIZE_MB * 1024 * 1024


def detect_image_extension(contents: bytes) -> str:
    """
    Xác định định dạng từ chính nội dung file (không tin tên file hay Content-Type do client gửi).
    Trả về phần mở rộng chuẩn hoặc báo lỗi 400 nếu không phải ảnh hợp lệ.
    """
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tệp tin ảnh rỗng (0 bytes).")
    if len(contents) > max_image_bytes():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dung lượng ảnh vượt quá giới hạn cho phép ({settings.MAX_IMAGE_SIZE_MB}MB).",
        )
    try:
        from PIL import Image

        with Image.open(io.BytesIO(contents)) as img:
            img.verify()
            image_format = (img.format or "").upper()
    except Exception:
        image_format = ""

    ext = _PIL_FORMAT_TO_EXT.get(image_format)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tệp tin không phải ảnh hợp lệ. Chỉ chấp nhận JPG, PNG, WEBP, GIF.",
        )
    return ext


def _cloudinary_enabled() -> bool:
    return (
        settings.STORAGE_BACKEND.lower() == "cloudinary"
        and bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)
    )


def save_venue_image(venue_id: int, contents: bytes) -> str:
    """
    Lưu ảnh theo STORAGE_BACKEND: "cloudinary" (nếu đủ khóa) hoặc "local" (/uploads/venues/...).
    Hàm này chặn (ghi đĩa / gọi HTTP) nên endpoint async phải gọi qua run_in_threadpool.
    """
    ext = detect_image_extension(contents)

    if _cloudinary_enabled():
        cloud_url = _upload_cloudinary(contents, venue_id, ext)
        if cloud_url:
            return cloud_url
        logger.warning("Upload Cloudinary thất bại, lưu ảnh cục bộ thay thế.")

    unique_filename = f"venue_{venue_id}_{uuid.uuid4().hex[:12]}{ext}"
    with open(os.path.join(VENUE_UPLOAD_DIR, unique_filename), "wb") as f:
        f.write(contents)
    return f"{LOCAL_URL_PREFIX}{unique_filename}"


def delete_venue_image_file(image_url: str) -> bool:
    """
    Xóa file ảnh khỏi nơi lưu trữ. Người gọi phải bảo đảm image_url thuộc đúng cụm sân
    mà người dùng có quyền (xem endpoint delete_venue_image).
    """
    if not image_url:
        return False

    if image_url.startswith(LOCAL_URL_PREFIX):
        filename = os.path.basename(image_url)
        safe_path = os.path.abspath(os.path.join(VENUE_UPLOAD_DIR, filename))
        if os.path.commonpath([VENUE_UPLOAD_DIR, safe_path]) != VENUE_UPLOAD_DIR:
            logger.warning("Chặn yêu cầu xóa file ngoài thư mục ảnh: %s", image_url)
            return False
        if os.path.exists(safe_path):
            try:
                os.remove(safe_path)
                return True
            except OSError as exc:
                logger.error("Không xóa được file ảnh %s: %s", safe_path, exc)
        return False

    if "res.cloudinary.com" in image_url and _cloudinary_enabled():
        return _delete_cloudinary(image_url)
    return False


def _cloudinary_signature(params: dict) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params)) + (settings.CLOUDINARY_API_SECRET or "")
    return hashlib.sha1(to_sign.encode("utf-8")).hexdigest()


def _upload_cloudinary(contents: bytes, venue_id: int, ext: str) -> Optional[str]:
    try:
        import httpx

        params = {
            "public_id": f"picklematch2k/venues/v{venue_id}_{uuid.uuid4().hex[:10]}",
            "timestamp": int(time.time()),
        }
        data = {**params, "api_key": settings.CLOUDINARY_API_KEY, "signature": _cloudinary_signature(params)}
        url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data=data, files={"file": (f"venue{ext}", contents)})
        if resp.status_code in (200, 201):
            return resp.json().get("secure_url")
        logger.warning("Cloudinary trả về mã %s", resp.status_code)
    except Exception as exc:
        logger.warning("Lỗi upload Cloudinary: %s", exc)
    return None


def _delete_cloudinary(image_url: str) -> bool:
    match = re.search(r"/upload/(?:v\d+/)?(picklematch2k/venues/[^.]+)", image_url)
    if not match:
        return False
    try:
        import httpx

        params = {"public_id": match.group(1), "timestamp": int(time.time())}
        data = {**params, "api_key": settings.CLOUDINARY_API_KEY, "signature": _cloudinary_signature(params)}
        url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/destroy"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, data=data)
        return resp.status_code == 200
    except Exception as exc:
        logger.warning("Không xóa được ảnh Cloudinary: %s", exc)
        return False
