#!/usr/bin/env python3

"""
Beszel API probe for HomeLab Portal.
HomeLab Portal 的 Beszel API 连通性测试工具。

Credentials are requested interactively and are NOT saved to disk.
账号密码仅在运行时输入，不写入磁盘。
"""

import argparse
import getpass
import json
import sys

from pathlib import Path

# Allow execution from the tools/ directory.
# 允许 tools/ 下的脚本导入项目根目录模块。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from beszel_client import BeszelAPIError, BeszelClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8090",
        help="Beszel Hub base URL",
    )
    args = parser.parse_args()

    print()
    print("Beszel Hub:", args.url)
    print()
    print(
        "请输入你平时登录 Beszel Web UI 的账号。"
    )
    print(
        "The password will NOT be displayed or saved."
    )
    print()

    email = input("Beszel email: ").strip()
    password = getpass.getpass("Beszel password: ")

    client = BeszelClient(args.url)

    try:
        client.authenticate_with_password(
            email=email,
            password=password,
        )

        systems = client.get_snapshot()

    except BeszelAPIError as exc:
        print()
        print("ERROR:")
        print(exc)
        return 1

    print()
    print("============================================================")
    print(" BESZEL API CONNECTION SUCCESSFUL")
    print(" Beszel API 已成功连接")
    print("============================================================")
    print()
    print(f"Systems returned: {len(systems)}")
    print()

    # Print only operational data.
    # 不输出密码或认证 Token。
    print(
        json.dumps(
            systems,
            indent=2,
            ensure_ascii=False,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
