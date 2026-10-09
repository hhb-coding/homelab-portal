"""
HomeLab Portal - Beszel API Client
HomeLab Portal - Beszel API 客户端

This module isolates all Beszel/PocketBase API communication so that
future Beszel API changes only need to be handled in one place.

本模块集中处理所有 Beszel/PocketBase API 通信。
这样未来 Beszel API 如果发生变化，只需要修改这里，
而不需要修改 Dashboard 前端或其他业务代码。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import requests


class BeszelAPIError(RuntimeError):
    """Raised when communication with the Beszel API fails.
    Beszel API 通信失败时抛出的异常。
    """


class BeszelClient:
    """Small wrapper around the Beszel / PocketBase REST API.

    Beszel / PocketBase REST API 的轻量封装。
    """

    def __init__(self, base_url: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "HomeLab-Portal/1.0",
            }
        )

    def _check_response(self, response: requests.Response) -> Dict[str, Any]:
        """Validate an HTTP response and return JSON.
        检查 HTTP 返回状态并解析 JSON。
        """

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            body = response.text[:500]
            raise BeszelAPIError(
                f"Beszel API request failed: "
                f"HTTP {response.status_code} - {body}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise BeszelAPIError(
                "Beszel returned a non-JSON response."
            ) from exc

    def authenticate_with_password(self, email: str, password: str) -> None:
        """Authenticate using a normal Beszel user account.

        使用 Beszel 普通用户账号进行认证。
        Password/token is never printed by this client.
        本客户端不会打印密码或 Token。
        """

        url = (
            f"{self.base_url}"
            "/api/collections/users/auth-with-password"
        )

        response = self.session.post(
            url,
            params={"fields": "token"},
            json={
                "identity": email,
                "password": password,
            },
            timeout=self.timeout,
        )

        payload = self._check_response(response)
        token = payload.get("token")

        if not token:
            raise BeszelAPIError(
                "Authentication succeeded but no token was returned."
            )

        self.session.headers.update(
            {"Authorization": f"Bearer {token}"}
        )

    def authenticate_with_token(self, token: str) -> None:
        """Authenticate using an existing PocketBase/Beszel token.

        使用已有 Beszel/PocketBase Token。
        """

        self.session.headers.update(
            {"Authorization": f"Bearer {token}"}
        )

    def get_systems(self) -> List[Dict[str, Any]]:
        """Return systems visible to the authenticated user.

        返回当前用户有权限读取的 Beszel 系统列表。
        """

        url = f"{self.base_url}/api/collections/systems/records"

        response = self.session.get(
            url,
            params={
                "page": 1,
                "perPage": 200,
                "fields": "id,name,host,port,status,info",
            },
            timeout=self.timeout,
        )

        payload = self._check_response(response)
        return payload.get("items", [])

    def get_latest_stats(
        self,
        system_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the newest one-minute stats record for one system.

        获取指定设备最新的一条 1 分钟粒度性能记录。
        """

        url = (
            f"{self.base_url}"
            "/api/collections/system_stats/records"
        )

        response = self.session.get(
            url,
            params={
                "page": 1,
                "perPage": 1,
                "sort": "-created",
                "filter": (
                    f"type='1m' && system='{system_id}'"
                ),
                "fields": "id,system,type,created,stats",
            },
            timeout=self.timeout,
        )

        payload = self._check_response(response)
        items = payload.get("items", [])

        if not items:
            return None

        return items[0]

    @staticmethod
    def _capacity(value: Any, positive: bool = False) -> Optional[float]:
        """Validate GiB metrics without coercing strings/bools / 严格验证 GiB 容量。"""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            number = float(value)
        except (OverflowError, ValueError):
            return None
        if not math.isfinite(number) or number < 0 or (positive and number == 0):
            return None
        return number

    @classmethod
    def capacity_metrics(cls, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Use one primary-filesystem sample, never sum efs / 仅使用同一主文件系统样本。"""
        total = cls._capacity(stats.get("d"), positive=True)
        used = cls._capacity(stats.get("du"))
        percent = cls._capacity(stats.get("dp"))
        if total is None or (used is not None and used > total):
            used = None
            percent = None
        if percent is not None and percent > 100:
            percent = None
        if used is None:
            percent = None
        return {
            "memory_total": cls._capacity(stats.get("m"), positive=True),
            "disk_total": total,
            "disk_used": used,
            # Beszel does not export Free/Bavail; reserved blocks matter.
            # Beszel 未导出 Free/Bavail；保留块使 total-used 不等于可用空间。
            "disk_available": None,
            "disk_usage_percent": percent,
            "capacity_unit": "GiB",
        }

    @staticmethod
    def _metric(
        info: Dict[str, Any],
        key: str,
    ) -> Any:
        """Safely retrieve a metric from Beszel's compact info object.

        安全读取 Beszel info 中的压缩字段。
        """

        return info.get(key)

    def get_snapshot(self) -> List[Dict[str, Any]]:
        """Return a normalized lightweight snapshot of all systems.

        返回统一格式的轻量设备快照。
        This is the structure HomeLab Portal will consume later.
        后续 HomeLab Portal 将直接使用这一层数据结构。
        """

        result: List[Dict[str, Any]] = []

        for system in self.get_systems():
            system_id = system.get("id")
            info = system.get("info") or {}

            latest = None
            if system_id:
                latest = self.get_latest_stats(system_id)

            stats = {}
            stats_created = None

            if latest:
                stats = latest.get("stats") or {}
                stats_created = latest.get("created")

            if not isinstance(stats, dict):
                stats = {}

            result.append(
                {
                    **self.capacity_metrics(stats),
                    "beszel_system_id": system_id,
                    "name": system.get("name"),
                    "status": system.get("status"),
                    "host": system.get("host"),
                    "port": system.get("port"),

                    # Current metrics from Beszel systems.info
                    # Beszel systems.info 中的实时核心指标
                    "cpu_percent": self._metric(info, "cpu"),
                    "memory_percent": self._metric(info, "mp"),
                    "disk_percent": self._metric(info, "dp"),

                    # Load averages / 系统负载
                    # Beszel stores Linux load averages in the compact
                    # "la" field, normally as [1m, 5m, 15m].
                    # Beszel 将 Linux Load Average 压缩存放在 "la" 字段中，
                    # 通常依次表示 1分钟、5分钟、15分钟负载。
                    "load_1": (
                        info.get("la", [None, None, None])[0]
                        if isinstance(info.get("la"), list)
                        and len(info.get("la")) > 0
                        else None
                    ),
                    "load_5": (
                        info.get("la", [None, None, None])[1]
                        if isinstance(info.get("la"), list)
                        and len(info.get("la")) > 1
                        else None
                    ),
                    "load_15": (
                        info.get("la", [None, None, None])[2]
                        if isinstance(info.get("la"), list)
                        and len(info.get("la")) > 2
                        else None
                    ),

                    "uptime_seconds": self._metric(info, "u"),
                    "temperature": self._metric(info, "dt"),

                    # Used only for compatibility/debugging.
                    # 用于兼容性检查和调试。
                    "info_keys": sorted(info.keys()),
                    "latest_stats_created": stats_created,
                    "stats_keys": sorted(stats.keys()),
                }
            )

        return result
