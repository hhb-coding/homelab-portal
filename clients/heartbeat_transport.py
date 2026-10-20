"""Shared standard-library transport / 共享标准库认证传输。"""
import json
import urllib.request


def send_json(url, token, payload):
    request = urllib.request.Request(url, data=json.dumps(payload, allow_nan=False).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json", "X-Heartbeat-Token": token})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read(128 * 1024))
