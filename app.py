"""
HomeLab Portal
==============

Lightweight HomeLab device and monitoring dashboard.
轻量级家庭实验室设备与监控门户。
"""

from hmac import compare_digest

import config
from beszel_client import BeszelAPIError, BeszelClient
from flask import Flask, jsonify, render_template, request

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


@app.route("/lite")
def lite():
    """Compact live view without history / 无历史图表的轻量实时视图。"""
    return render_template("lite.html", app_name=config.APP_NAME)


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



@app.route("/api/metrics")
def metrics():
    """
    Return normalized system metrics from Beszel.

    返回经过 HomeLab Portal 标准化处理后的
    Beszel 系统性能指标。

    This endpoint intentionally does not expose Beszel credentials,
    authentication tokens, or other secrets.

    本接口不会向浏览器暴露 Beszel 的账号、密码或 Token。
    """

    client = BeszelClient(
        config.BESZEL_URL,
        timeout=config.BESZEL_TIMEOUT,
    )

    try:
        # Prefer token authentication when configured.
        # 如果配置了 Token，则优先使用 Token。
        if config.BESZEL_TOKEN:
            client.authenticate_with_token(
                config.BESZEL_TOKEN
            )

        # Otherwise use the normal Beszel account.
        # 否则使用普通 Beszel 登录账号。
        elif (
            config.BESZEL_EMAIL
            and config.BESZEL_PASSWORD
        ):
            client.authenticate_with_password(
                config.BESZEL_EMAIL,
                config.BESZEL_PASSWORD,
            )

        else:
            return jsonify(
                {
                    "status": "error",
                    "error": (
                        "beszel_credentials_not_configured"
                    ),
                }
            ), 503

        systems = client.get_snapshot()

        return jsonify(
            {
                "status": "ok",
                "source": "beszel",
                "count": len(systems),
                "systems": systems,
            }
        )

    except BeszelAPIError as exc:
        # Log only the API error.
        # Never log credentials or authentication tokens.
        # 只记录 API 错误，绝不记录认证信息。
        app.logger.warning(
            "Beszel API error: %s",
            exc,
        )

        return jsonify(
            {
                "status": "error",
                "error": "beszel_api_unavailable",
            }
        ), 502



@app.route("/api/dashboard")
def dashboard_api():
    """
    Return unified HomeLab Portal device information.

    返回 HomeLab Portal 统一设备信息：
    IP/ZeroTier/Last Seen + Beszel metrics.
    """

    # Local import intentionally keeps the integration modular.
    # 使用局部 import，使 Dashboard 模块保持独立。
    from dashboard_service import build_dashboard

    data = build_dashboard()

    return jsonify(data)


@app.route("/api/history")
def history_api():
    """
    Return persistent historical metrics from Beszel.
    返回来自 Beszel 的持久化历史性能指标。
    """
    from history_service import build_history

    minutes_raw = request.args.get("minutes", "60")

    try:
        minutes = int(minutes_raw)
    except (TypeError, ValueError):
        minutes = 60

    try:
        return jsonify(build_history(minutes=minutes))
    except BeszelAPIError as exc:
        app.logger.warning("Beszel history API error: %s", exc)
        return jsonify(
            {
                "status": "error",
                "error": "beszel_history_unavailable",
            }
        ), 502


if __name__ == "__main__":
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
    )
