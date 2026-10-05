"""
HomeLab Portal
==============

Lightweight HomeLab device and monitoring dashboard.
轻量级家庭实验室设备与监控门户。
"""

from hmac import compare_digest

from flask import Flask, jsonify, render_template, request

import config
from db import (
    database_is_ready,
    get_device,
    init_db,
    list_devices,
    upsert_device,
)


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


@app.route("/api/devices")
def devices():
    """
    Return all registered HomeLab devices.
    返回所有已经登记的 HomeLab 设备。
    """

    return jsonify(
        {
            "devices": list_devices(),
        }
    )


@app.route("/api/devices/<device_id>")
def device(device_id):
    """
    Return one registered HomeLab device.
    返回指定的 HomeLab 设备。
    """

    result = get_device(device_id)

    if result is None:
        return jsonify({"error": "device_not_found"}), 404

    return jsonify(result)


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """
    Receive a heartbeat from a HomeLab device.

    接收 HomeLab 设备发送的 heartbeat。

    Expected header:
        X-Heartbeat-Token

    Example JSON body:
        {
            "device_id": "example-device",
            "hostname": "example-host",
            "display_name": "Example Device",
            "lan_ip": "192.168.1.10",
            "zerotier_ip": null
        }
    """

    # Refuse heartbeat traffic if the server has no configured token.
    # 如果服务器没有配置 Token，则拒绝 heartbeat 请求。
    if not config.HEARTBEAT_TOKEN:
        return (
            jsonify(
                {
                    "error": "heartbeat_not_configured",
                    "message": "HEARTBEAT_TOKEN is not configured.",
                }
            ),
            503,
        )

    provided_token = request.headers.get("X-Heartbeat-Token", "")

    # Use constant-time comparison for the shared token.
    # 使用恒定时间比较，避免普通字符串比较带来的时序差异。
    if not provided_token or not compare_digest(
        provided_token,
        config.HEARTBEAT_TOKEN,
    ):
        return (
            jsonify(
                {
                    "error": "unauthorized",
                    "message": "Invalid heartbeat token.",
                }
            ),
            401,
        )

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return (
            jsonify(
                {
                    "error": "invalid_json",
                    "message": "Request body must contain a JSON object.",
                }
            ),
            400,
        )

    device_id = payload.get("device_id")

    if not isinstance(device_id, str) or not device_id.strip():
        return (
            jsonify(
                {
                    "error": "missing_device_id",
                    "message": "device_id is required.",
                }
            ),
            400,
        )

    device_id = device_id.strip()

    result = upsert_device(
        device_id=device_id,
        hostname=payload.get("hostname"),
        display_name=payload.get("display_name"),
        lan_ip=payload.get("lan_ip"),
        zerotier_ip=payload.get("zerotier_ip"),
    )

    return jsonify(
        {
            "status": "ok",
            "device_id": device_id,
            "created": result["created"],
            "lan_ip_changed": result["lan_ip_changed"],
            "zerotier_ip_changed": result["zerotier_ip_changed"],
        }
    )


if __name__ == "__main__":
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
    )
