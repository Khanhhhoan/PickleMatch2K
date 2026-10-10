from pathlib import Path
from typing import List, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent

# Giá trị mẫu không được phép dùng làm SECRET_KEY khi chạy production
_PLACEHOLDER_SECRET_MARKERS = ("change_in_production", "changeme", "your-secret")

# Cho phép truy cập từ điện thoại trong mạng LAN khi phát triển
_DEV_LAN_ORIGIN_REGEX = (
    r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"
)


class Settings(BaseSettings):
    PROJECT_NAME: str = "PickleMatch2K"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development | production | test

    # SECURITY
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    BCRYPT_ROUNDS: int = 12
    LOGIN_MAX_ATTEMPTS: int = 10
    LOGIN_WINDOW_SECONDS: int = 300
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"
    CORS_ORIGIN_REGEX: Optional[str] = None

    # DATABASE (PostgreSQL; SQLite chỉ dùng khi khai báo rõ ràng sqlite:///...)
    DATABASE_URL: str
    REDIS_URL: Optional[str] = None

    # STORAGE (local | cloudinary)
    STORAGE_BACKEND: str = "local"
    MAX_IMAGE_SIZE_MB: int = 10
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    # SEPAY
    SEPAY_WEBHOOK_API_KEY: Optional[str] = None
    SEPAY_BANK_NAME: str = ""
    SEPAY_BANK_CODE: str = ""
    SEPAY_BANK_ACCOUNT: str = ""
    SEPAY_ACCOUNT_HOLDER: str = ""
    # true: mọi cụm sân dùng chung tài khoản SEPAY_* ở trên; false: dùng tài khoản của từng chủ sân
    SEPAY_UNIFIED_TEST_MODE: bool = True
    # Chỉ bật khi demo/kiểm thử: cho phép giả lập thanh toán không cần chuyển khoản thật
    SEPAY_SIMULATOR_ENABLED: bool = False

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(str(ROOT_DIR / ".env"), str(BACKEND_DIR / ".env")),
        extra="ignore",
    )

    @field_validator(
        "REDIS_URL", "CORS_ORIGIN_REGEX", "SEPAY_WEBHOOK_API_KEY",
        "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        value = value.strip()
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                # Dùng driver psycopg 3 (gói psycopg[binary] trong requirements.txt)
                return "postgresql+psycopg://" + value[len(prefix):]
        if value.startswith("sqlite:///") and not value.startswith("sqlite:////"):
            relative = value[len("sqlite:///"):]
            if relative and not Path(relative).is_absolute():
                return f"sqlite:///{(BACKEND_DIR / relative).resolve().as_posix()}"
        return value

    @model_validator(mode="after")
    def _check_secret_key(self):
        if len(self.SECRET_KEY) < 16:
            raise ValueError("SECRET_KEY phải dài ít nhất 16 ký tự.")
        if self.is_production and any(m in self.SECRET_KEY.lower() for m in _PLACEHOLDER_SECRET_MARKERS):
            raise ValueError("SECRET_KEY đang là giá trị mẫu. Hãy đặt khóa ngẫu nhiên trước khi chạy production.")
        return self

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def cors_origin_regex(self) -> Optional[str]:
        if self.CORS_ORIGIN_REGEX:
            return self.CORS_ORIGIN_REGEX
        return None if self.is_production else _DEV_LAN_ORIGIN_REGEX


settings = Settings()
