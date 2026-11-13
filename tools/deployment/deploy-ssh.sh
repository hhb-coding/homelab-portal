#!/usr/bin/env bash
# Run as daniel in an ordinary SSH login on hp-linux. No sudo is required.
# Only Portal Web is restarted; existing collectors/timers run on their schedule.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1

B=${PORTAL_DEPLOY_PACKAGE:?Prepared package required}
P=/home/daniel/homelab-portal
BASE=10875361198982d2135bc168ca686e929460addf
TARGET=${PORTAL_DEPLOY_TARGET:?Exact merge SHA required}
export PORTAL_DEPLOY_TARGET
PY="$P/.venv/bin/python"
SUPPORT="$B/deploy-support.py"
DROP=/home/daniel/.config/systemd/user/homelab-portal.service.d/90-endpoint-b-discovery.conf
STATE=/home/daniel/.config/homelab-portal/endpoint-b/state.json
RUN=''
mutated=0
accepted=0
rollback_result='未执行'
node_bin=''

note() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; }
die() { note "$*" >&2; exit 1; }

rollback() {
    # Keep the target's version-aware v3 collector even when restoring the old UI.
    # No SQLite file is copied, restored, migrated, truncated or deleted.
    local result=0
    note '部署或验收失败；保留私有状态，按既有回退包恢复 Web 与本机补丁，保留 v3 兼容采集器。'
    systemctl --user show homelab-metrics-archive.timer -p LastTriggerUSecMonotonic --value >"$RUN/rollback-timer-trigger.private.txt" || result=1
    if [[ -f "$STATE" ]]; then
        cp -p -- "$STATE" "$RUN/endpoint-b.failed.private.json" || result=1
    fi
    systemctl --user show homelab-portal.service >"$RUN/web-failed.private.txt" 2>&1 || true
    journalctl --user -u homelab-portal.service --since '-40min' --no-pager >"$RUN/web-failed-journal.private.txt" 2>&1 || true
    # Restore the prepared private files from the verified package.
    install -m 600 "$B/private-config/.env" "$P/.env" || result=1
    for name in archive.env network-archive-roles.json network-tplink-scan.json; do
        install -m 600 "$B/private-config/$name" "/home/daniel/.config/homelab-portal/$name" || result=1
    done
    rm -f -- "$DROP" || result=1
    # Serialize the code change with the existing collector's writer lock.
    if flock -w 900 8; then
        if git -C "$P" reset --hard "$BASE" && git -C "$P" apply "$B/production.patch"; then
            install -m 644 "$RUN/compat-network_archive.py" "$P/network_archive.py" || result=1
            "$PY" -B - "$B" "$P" "$RUN" <<'PY' || result=1
import json,sys
from pathlib import Path
b,p,r=map(Path,sys.argv[1:])
m=json.loads((b/'manifest.private.json').read_text())
for name in m['modified_files']:
    assert (p/name).read_bytes()==(b/'original'/name).read_bytes(),name
for name in m['untracked_files']:
    assert (p/name).read_bytes()==(b/'untracked'/name).read_bytes(),name
assert (p/'network_archive.py').read_bytes()==(r/'compat-network_archive.py').read_bytes()
PY
        else
            result=1
        fi
        flock -u 8 || result=1
    else
        result=1
    fi
    systemctl --user daemon-reload || result=1
    systemctl --user restart homelab-portal.service || result=1
    "$PY" -B "$SUPPORT" health "$RUN" rollback || result=1
    if [[ "$result" == 0 ]]; then
        rollback_result='已恢复原 Web 与本机补丁，保留 v3 兼容采集器；回退健康复核通过'
        printf '%s\n' "$rollback_result" >"$RUN/rollback-result.private.txt"
    else
        rollback_result='回退或复核失败，须检查本次运行日志'
        printf '%s\n' "$rollback_result" >"$RUN/rollback-result.private.txt"
    fi
    return "$result"
}

on_exit() {
    local status=$? version
    trap - EXIT INT TERM HUP
    set +e
    if [[ "$mutated" == 1 && "$accepted" != 1 ]]; then
        rollback
        status=1
    fi
    version=$(git -C "$P" rev-parse HEAD 2>/dev/null)
    if [[ "$accepted" == 1 ]]; then
        printf '生产版本：%s＋本机补丁；验收：真实 TP-Link/HP ICMP 映射、Endpoint B 卡片与曲线新样本、CPU 历史、归档 timer 和 Web 健康全部通过。\n' "$version"
    elif [[ "$mutated" == 1 ]]; then
        printf '生产版本：%s；验收：部署未通过，%s。\n' "$version" "$rollback_result"
    else
        printf '生产版本：%s；验收：部署前检查未通过，生产未变更（日志：%s）。\n' "$version" "${RUN:-无}"
    fi
    exit "$status"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

[[ $(id -un) == daniel && $(hostname -s) == hp-linux ]] || die '必须在 HP 的 daniel 普通 SSH 登录中运行。'
[[ $# == 0 ]] || die '此脚本不接受参数；运行目录和目标版本已固定。'
for dependency in git python3 systemctl journalctl flock curl findmnt sha256sum timeout install tee; do
    command -v "$dependency" >/dev/null || die "缺少命令：$dependency"
done
[[ -x "$PY" ]] || die '生产 Python 虚拟环境不可用。'
exec 9>"$B/deploy.lock"
flock -n 9 || die '已有部署在运行。'
cd "$B"
sha256sum --check --quiet execution-assets.sha256
RUN=$(mktemp -d "$B/ssh-run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXXXX")
chmod 700 "$RUN"
exec > >(tee -a "$RUN/execution.private.log") 2>&1
note "本次私有证据目录：$RUN"

if command -v node >/dev/null; then
    node_bin=$(command -v node)
else
    node_bin=/home/daniel/.nvm/versions/node/v22.23.3/bin/node
fi
[[ -x "$node_bin" ]] || die 'Node.js 不可用。'
"$node_bin" --check "$B/accept-live.cjs"
"$PY" -B "$SUPPORT" offline
"$PY" -B "$SUPPORT" identity "$RUN"
git -C "$P" bundle verify "$B/rollback.bundle" >"$RUN/bundle-verification.private.txt" 2>&1

note '获取远端 main，并核对完整目标 SHA。'
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=15}"
[[ $(git -C "$P" remote get-url origin) == git@github.com:hhb-coding/homelab-portal.git ]] || die 'origin URL 与预检不符。'
GIT_TERMINAL_PROMPT=0 git -C "$P" fetch --no-tags origin '+refs/heads/main:refs/remotes/origin/main'
[[ $(git -C "$P" rev-parse refs/remotes/origin/main) == "$TARGET" ]] || die 'origin/main 已变化，停止部署。'
[[ $(git -C "$P" ls-remote --exit-code origin refs/heads/main | cut -f1) == "$TARGET" ]] || die '远端 main 与已获取目标不符。'
git -C "$P" merge-base --is-ancestor "$BASE" "$TARGET"

note '在临时克隆中再次验证原补丁恢复和目标补丁；生产尚未修改。'
git clone --quiet --no-hardlinks "$B/rollback.bundle" "$RUN/restore-check"
git -C "$RUN/restore-check" apply --check "$B/production.patch"
git -C "$RUN/restore-check" apply "$B/production.patch"
"$PY" -B - "$B" "$RUN/restore-check" <<'PY'
import json,sys
from pathlib import Path
b,t=map(Path,sys.argv[1:])
for name in json.loads((b/'manifest.private.json').read_text())['modified_files']:
    assert (t/name).read_bytes()==(b/'original'/name).read_bytes(),name
PY
git clone --quiet --no-hardlinks "$P" "$RUN/stage"
git -C "$RUN/stage" checkout --quiet --detach "$TARGET"
"$PY" -B - "$B" "$RUN/stage" <<'PY'
import json,sys,hashlib
from pathlib import Path
b,t=map(Path,sys.argv[1:])
for name,expected in json.loads((b/'target-tree.sha256.json').read_text()).items():
    assert hashlib.sha256((t/name).read_bytes()).hexdigest()==expected,name
PY
git -C "$RUN/stage" apply --check "$B/production-on-pr30.patch"
git -C "$RUN/stage" apply "$B/production-on-pr30.patch"
git -C "$RUN/stage" diff --check
cp -p "$RUN/stage/network_archive.py" "$RUN/compat-network_archive.py"
# Adapt two upstream assertions to the pre-existing, preserved local behavior:
# the cache marker and Dell history support. No assertions are removed.
"$PY" -B - "$RUN/stage" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])/'tests/test_performance_history.js';s=p.read_text()
old="? 'network-quality-layout' : '7071-device-y-axis'"
assert s.count(old)==1
p.write_text(s.replace(old,"? 'network-quality-layout' : '7072-frequency-range'"))
p=Path(sys.argv[1])/'tests/test_performance_history.py';s=p.read_text()
old="self.assertIsNone(device_role({'device_id': 'example-dell'}, 'local'))"
assert s.count(old)==1
p.write_text(s.replace(old,"self.assertEqual(device_role({'device_id': 'example-dell'}, 'local'), 'dell')"))
PY
cp -p "$RUN/stage/tests/test_performance_history.js" "$RUN/test-performance-local-cache.js"
cp -p "$RUN/stage/tests/test_performance_history.py" "$RUN/test-performance-local-dell.py"
(
    cd "$RUN/stage"
    "$PY" -B -m unittest discover -s tests -v >"$RUN/python-tests.private.log" 2>&1
    "$node_bin" tests/test_performance_history.js >"$RUN/js-performance.private.log" 2>&1
    "$node_bin" tests/test_network_readability.js >"$RUN/js-network.private.log" 2>&1
)
# Exercise the exact old-Web/new-collector rollback combination before deployment.
cp -p "$RUN/compat-network_archive.py" "$RUN/restore-check/network_archive.py"
(
    cd "$RUN/restore-check"
    "$PY" -B -m unittest discover -s "$RUN/stage/tests" -p test_network_archive.py \
        -k multiple_rebindings -k versions_binding -v >"$RUN/rollback-compat.private.log" 2>&1
)
timeout 90s "$node_bin" "$B/accept-live.cjs" "$RUN" --probe

if [[ -f "$STATE" ]]; then cp -p -- "$STATE" "$RUN/endpoint-b-before.private.json"; fi
note '保存在线服务/timer、CPU 与只读归档基线。'
"$PY" -B "$SUPPORT" snapshot "$RUN"
git -C "$P" status --porcelain=v1 >"$RUN/git-status.private.txt"
git -C "$P" show-ref >"$RUN/git-refs.private.txt"
git -C "$P" diff --binary HEAD >"$RUN/local-before.patch"
cp -a /home/daniel/.config/systemd/user/homelab-portal.service "$RUN/"
cp -a /home/daniel/.config/systemd/user/homelab-portal.service.d "$RUN/web-dropins-before"
# Obtain the checked HDD lock path without sourcing private shell content.
archive_lock=$("$PY" -B - /home/daniel/.config/homelab-portal/archive.env <<'PY'
from dotenv import dotenv_values
import sys
print(dotenv_values(sys.argv[1])['METRICS_ARCHIVE_PATH']+'.lock')
PY
)
[[ -f "$archive_lock" && ! -L "$archive_lock" ]] || die '现有归档锁不可用。'
exec 8<>"$archive_lock"
flock -w 900 8
# Recheck immediately before mutation; refuse any newly edited files/configuration.
"$PY" -B "$SUPPORT" offline
[[ $(git -C "$P" rev-parse refs/remotes/origin/main) == "$TARGET" ]] || die '本地 origin/main 在预检期间变化。'
[[ $(git -C "$P" ls-remote --exit-code origin refs/heads/main | cut -f1) == "$TARGET" ]] || die '远端 main 在预检期间变化。'
note '部署指定提交并应用已合并的本机补丁。'
mutated=1
touch "$RUN/production-mutation-started"
git -C "$P" reset --hard "$TARGET"
git -C "$P" apply "$B/production-on-pr30.patch"
git -C "$P" diff --check
"$PY" -B - "$B" "$P" "$RUN/stage" <<'PY'
import json,sys
from pathlib import Path
b,p,t=map(Path,sys.argv[1:])
for name in json.loads((b/'manifest.private.json').read_text())['modified_files']:
    assert (p/name).read_bytes()==(t/name).read_bytes(),name
PY
install -m 600 "$B/90-endpoint-b-discovery.conf.prepared" "$DROP"
flock -u 8
systemctl --user daemon-reload
systemctl --user restart homelab-portal.service
"$PY" -B "$SUPPORT" health "$RUN" deployed

note '通过生产页面实际点击发现和保存，并等待自然归档；不创建或修改 Beszel 探测。'
timeout --signal=TERM --kill-after=15s 37m "$node_bin" "$B/accept-live.cjs" "$RUN"
# A successful page can precede completion of the running archive pass.
deadline=$((SECONDS + 900))
while [[ $(systemctl --user show homelab-metrics-archive.service -p ActiveState --value) == activating ]]; do
    (( SECONDS < deadline )) || die '归档任务未按时完成。'
    sleep 5
done
"$PY" -B "$SUPPORT" final "$RUN"
[[ $(git -C "$P" rev-parse HEAD) == "$TARGET" ]] || die '最终生产 HEAD 不符。'
"$PY" -B - "$B" "$P" "$RUN/stage" <<'PY'
import json,sys
from pathlib import Path
b,p,t=map(Path,sys.argv[1:])
for name in json.loads((b/'manifest.private.json').read_text())['modified_files']:
    assert (p/name).read_bytes()==(t/name).read_bytes(),name
PY
git -C "$P" status --short >"$RUN/git-status-after.private.txt"
touch "$RUN/accepted"
accepted=1
note "验收证据已保存：$RUN/acceptance.private.json；截图：active-1440.png、active-390.png。"
