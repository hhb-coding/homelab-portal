"""
HomeLab Portal
==============

Lightweight HomeLab device and monitoring dashboard.
轻量级家庭实验室设备与监控门户。
"""

from flask import Flask, jsonify, render_template

import config
from db import database_is_ready, init_db


app = Flask(__name__)


# Initialize SQLite when the application starts.
# 应用启动时自动初始化 SQLite 数据库。
init_db()


@app.route("/")
def index():
    """
    Main HomeLab Portal page.
    HomeLab Portal 首页。
    """

    return render_template(
        "index.html",
        app_name=config.APP_NAME,
        database_ready=database_is_ready(),
    )


@app.route("/api/health")
def health():
    """
    Lightweight health endpoint.
    轻量级服务健康检查接口。
    """

    return jsonify(
        {
            "service": config.APP_NAME,
            "status": "ok",
            "database": "ok" if database_is_ready() else "error",
        }
    )


if __name__ == "__main__":
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
    )
