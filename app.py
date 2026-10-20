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


@app.route("/api/telemetry/cpu-frequency", methods=["POST"])
def cpu_frequency_receive():
    """Authenticated inbox, independent of Heartbeat / 独立认证接收，不更新心跳。"""
    from frequency import TelemetryError, receive
    import sqlite3
    if not config.HEARTBEAT_TOKEN:
        return jsonify(error="heartbeat_not_configured"), 503
    token = request.headers.get("X-Heartbeat-Token", "")
    if not token or not compare_digest(token.encode("utf-8"), config.HEARTBEAT_TOKEN.encode("utf-8")):
        return jsonify(error="unauthorized"), 401
    if request.content_length is None or request.content_length > 128 * 1024:
        return jsonify(error="body_too_large"), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"device_id", "samples"}:
        return jsonify(error="invalid_payload"), 400
    try:
        return jsonify(receive(config.DATABASE_PATH, payload["device_id"], payload["samples"]))
    except TelemetryError as exc:
        return jsonify(error=exc.code), exc.status
    except sqlite3.Error:
        return jsonify(error="queue_unavailable"), 503


@app.route("/api/history/v2")
def archive_history_api():
    """Read-only, paged frequency contract for 7.06 / 分页只读频率历史。"""
    from contextlib import closing
    import os
    from pathlib import Path
    import sqlite3
    from frequency import TelemetryError
    from frequency_history import query
    from metrics_archive import require_hdd
    if not config.FREQUENCY_HISTORY_ENABLED:
        return jsonify(error="archive_history_disabled"), 503
    device_id = request.args.get("device_id", "")
    if get_device(device_id) is None:
        return jsonify(error="device_not_found"), 404
    if request.args.get("metric", "cpu_frequency_ghz") != "cpu_frequency_ghz":
        return jsonify(error="unsupported_metric"), 400
    try:
        database = Path(os.getenv("METRICS_ARCHIVE_PATH", "/srv/data/homelab-portal-archive/metrics.sqlite3"))
        require_hdd(database, Path(os.getenv("METRICS_ARCHIVE_MOUNT", "/srv/data")), os.getenv("METRICS_ARCHIVE_UUID", ""))
        with closing(sqlite3.connect(database.resolve().as_uri()+"?mode=ro", uri=True, timeout=2)) as conn:
            conn.execute("PRAGMA query_only=ON")
            result = query(conn, device_id, request.args.get("start"), request.args.get("end"),
                           request.args.get("cursor"), int(request.args.get("limit", "2000")))
        return jsonify(result)
    except TelemetryError as exc:
        return jsonify(error=exc.code), exc.status
    except (ValueError, TypeError):
        return jsonify(error="invalid_query"), 400
    except Exception:
        return jsonify(error="archive_unavailable"), 503


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
