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
