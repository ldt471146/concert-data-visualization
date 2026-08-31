import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "pulse-atlas-local-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'pulse_atlas.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
        # SQLite 无连接池收益，调大队列避免 14 个分析接口并发抢占连接导致 30s 超时
    # (QueuePool 默认 5+10 overflow；此处放宽到 20+40，timeout 放宽到 60s)
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": 20,
        "max_overflow": 40,
        "pool_timeout": 60,
    }
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "atlas")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "pulse2025")
