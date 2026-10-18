# Backend API PickleMatch2K (FastAPI + PostgreSQL). Dùng qua docker-compose.yml hoặc docker-compose.aws.yml ở thư mục gốc.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Cài thư viện trước để tận dụng cache khi chỉ đổi mã nguồn.
# Mọi gói trong requirements.txt đều có bản dựng sẵn cho Linux nên không cần gcc hay libpq-dev.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Chạy bằng tài khoản thường. Ứng dụng chỉ ghi vào hai thư mục: ảnh tải lên (uploads) và chứng từ hoàn tiền
# (private_uploads, không phục vụ công khai); thiếu quyền ghi thì tải chứng từ hoàn tiền sẽ lỗi.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads/venues /app/private_uploads/refund_proofs \
    && chown -R appuser:appuser /app/uploads /app/private_uploads
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

# 1) nâng schema lên bản mới nhất (CSDL trong container không có pg_dump nên bỏ bước tự sao lưu)
# 2) nạp dữ liệu demo nếu SEED_DEMO_DATA=true và CSDL còn trống
# 3) chạy API bằng một tiến trình, không --reload
CMD ["sh", "-c", "python manage.py migrate --no-backup && if [ \"$SEED_DEMO_DATA\" = \"true\" ]; then python manage.py seed --if-empty; fi && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
