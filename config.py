"""
HomeLab Portal configuration.
HomeLab Portal 配置模块。

Environment-specific values should be stored in .env.
与具体环境有关的配置应该存放在 .env 中，不应写死在代码里。
"""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

# Load local environment variables from .env.
# 从本地 .env 文件读取环境变量。
load_dotenv(BASE_DIR / ".env")


APP_NAME = os.getenv("APP_NAME", "HomeLab Portal")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8088"))

DEBUG = os.getenv("DEBUG", "false").lower() == "true"


# Database path can be configured through .env.
# 数据库路径可以通过 .env 配置。
_database_path = os.getenv("DATABASE_PATH", "data/homelab.db")

if os.path.isabs(_database_path):
    DATABASE_PATH = Path(_database_path)
else:
    DATABASE_PATH = BASE_DIR / _database_path


# Shared token used by heartbeat clients.
# Heartbeat 客户端与 Portal 共用的认证 Token。
HEARTBEAT_TOKEN = os.getenv("HEARTBEAT_TOKEN", "")

# --- Beszel integration / Beszel 集成 ---

# Internal address of the Beszel Hub.
# Beszel Hub 内部访问地址。
BESZEL_URL = os.getenv(
    "BESZEL_URL",
    "http://127.0.0.1:8090",
)

# Authentication credentials are loaded from .env only.
# 认证信息只从 .env 读取，不写入公开代码。
BESZEL_EMAIL = os.getenv("BESZEL_EMAIL", "")
BESZEL_PASSWORD = os.getenv("BESZEL_PASSWORD", "")
BESZEL_TOKEN = os.getenv("BESZEL_TOKEN", "")

# API request timeout in seconds.
# API 请求超时时间（秒）。
BESZEL_TIMEOUT = int(
    os.getenv("BESZEL_TIMEOUT", "10")
)
