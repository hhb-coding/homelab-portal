# Endpoint B: find TP-Link / 查找 TP-Link

[PR #30](https://github.com/hhb-coding/homelab-portal/pull/30) merged as
`b1de1f5`. HP passed live discovery, mapping and new-sample acceptance on
2026-11-13 with the [PR #31 deployment](network-quality-layout-acceptance.md#hp-production-acceptance).
The validation section below records the original synthetic HTTP and temporary
SQLite tests.

PR #30 已合并为 `b1de1f5`，并随 PR #31 于 2026-11-13 在 HP 完成实机验收，
覆盖查找、保存映射及新样本显示。下文保留原合成 HTTP 与临时 SQLite 测试记录。

## Behavior / 使用流程

Endpoint B has **查找 TP-Link**. The server reuses the tested HTTP-homepage fingerprint:
12 concurrent curl requests, 0.5-second connection and 1.5-second total deadlines,
case-insensitive `TL-WDR5620`. It does not require ping, authenticate to the router,
follow redirects, use proxies or mutate router/Beszel settings. Each response is
limited to 256 KiB; curl also ignores user curl configuration. Linux `curl` is required.

复用实测并行 HTTP 首页识别方式，按钮旁显示唯一发现的 IP 与“请在 Beszel 更新探测目标”，
并在 HP ICMP 探测下拉框预选该地址。操作流程：

1. Find the management IP. Zero matches explicitly says **未找到 TL-WDR5620**;
   multiple matches lists the IPs and requires verification. Neither permits saving.
2. With one match, the preselected IP initially says **等待 Beszel 更新** if there is
   no enabled ICMP monitor for that address on the privately configured HP system.
   Update Beszel Network Monitors manually; click **刷新探测** or wait for the
   15-second refresh. TCP/HTTP/DNS, disabled and other systems' monitors are excluded.
3. Exactly one eligible probe enables **保存映射**. Duplicate probes, expired discovery
   (>10 minutes), a conflicting Network role, or unavailable Beszel explicitly blocks saving.
4. Save writes only the new private Portal state file. The server rechecks the discovery
   receipt and current Beszel probe before saving. Until ingestion, show **映射已保存 ·
   等待首个归档样本** with empty metrics. The next normal archive run imports samples;
   card, plotted series and chart statistics use the same pinned archive identity and IP.
   Ordinary dashboard refresh then shows **映射已生效**. No sample is fabricated.

没有对应探测时等待 Beszel；检测到唯一启用的 HP ICMP 后才能保存。无结果、多结果、
重复探测、发现过期、角色冲突与上游失败均有明确状态。保存后等待既有归档任务入库，
首个样本通过同一次历史响应更新卡片与曲线。重新查找不自动改动已保存的映射。

## Private configuration / 私有配置

Keep the existing `NETWORK_HISTORY_ROLES_FILE` (falling back to
`NETWORK_ARCHIVE_ROLES_FILE`). Its `system_id` must identify **HP's Beszel system**.
The browser cannot select a system, supply scan addresses, ports or URLs.

Use these new optional settings in the Portal server's private environment:

```dotenv
NETWORK_TPLINK_SCAN_FILE=/absolute/private/network-tplink-scan.json
NETWORK_ENDPOINT_B_STATE_FILE=/absolute/private/endpoint-b-state.json
```

Copy [the scan example](../examples/network-tplink-scan.json) outside Git and replace
both placeholders privately. `start`/`end` are inclusive IPv4 addresses in the same
RFC1918 block, with at most 254 addresses. Public, loopback, link-local, IPv6, hostnames,
reversed/oversized ranges fail closed. There is no built-in production scan range.
The state parent directory must already exist and be private and writable by the
Portal process. Use a fresh state path; it must differ from the roles and scan files.

扫描范围只在服务器私有 JSON 中指定，起止均包含，最多254个 RFC1918 IPv4；示例占位值
必须私下替换。角色文件的 system_id 必须是 HP。新状态路径不可复用旧角色或扫描文件，
父目录预先创建并限制权限。默认不启用，无真实地址、ID 或凭据写入仓库。

The state has version 1, the latest discovery receipt, current pinned mapping and
previous mappings. Writes use a `0600` temporary file, fsync and atomic replacement;
a sibling `.lock` file protects scan/save across WSGI workers. Concurrent operations
are rejected; scans have a 30-second cooldown. Repeated identical saves are idempotent.
The original role file stays intact. The existing Portal trusted-access boundary
also covers these APIs: POST requires JSON plus a custom same-origin request header;
there is no new Portal login or credential entered into the browser.

状态原子保存为0600并保留旧映射；跨进程排他、防重复扫描，30秒冷却。POST 使用 JSON、
自定义请求头与 Origin 校验，沿用 Portal 既有可信访问入口。Beszel 只认证与 GET，不创建、
修改或停用任何上游探测。

## Archive compatibility / 归档兼容

No schema migration or new timer. Network schema remains v3, with existing raw TTL,
daily increments, checkpoints, events, HDD guards, locks and metrics/frequency paths.
History stays read-only. Portal mapping is a separate overlay for Endpoint B only;
it pins source monitor ID, system and target instead of relying on address alone.

An existing Beszel monitor can change target while retaining its upstream ID. The
collector now stores a separate local `binding_…` archive identity, preserves old
samples/daily/checkpoints/incidents, and disables only the old **local metadata**.
Its JSON retains the source monitor ID, binding generation and first allowed minute.
Only aggregates dated from the next complete UTC minute after observing the change
are accepted, excluding old and straddling aggregates. Further changes, including
returning to the previous address, create another version. Interval/enabled changes
alone do not split history. Upstream reads still use the original Beszel ID.

同一 Beszel ID 改址时，归档保留旧身份和全部样本、日汇总、断点、事件；新身份仅接收确认
改址后下一完整 UTC 分钟起的数据，旧故障不会被新地址的成功探测误判恢复。旧分钟聚合无法
证明其所属地址，因此改址到首次观测之间的数据不回填；卡片可能需等下一次归档任务。
原有90天网络分钟保留策略与性能/频率归档不变，不改归档 schema。

Rollback: retain a copy of the private state, then disable discovery by clearing its
scan-file setting; the saved history overlay continues while its state-file setting
is present. Clearing the state-file setting returns the reader to the original roles.
Keep v3 code that understands versioned bindings; an older collector fails closed
when a reused upstream ID differs from its old identity. Do not delete new archive
versions or restore an old SQLite backup merely to roll back the button.

回滚可关闭扫描配置并保留映射；清空状态文件配置可回到旧角色读取。旧版本采集器遇到改址
仍会拒绝该监控，因此应保留理解版本身份的 v3 代码；无需删归档或恢复旧库来撤回按钮。

## Validation and previews / 验证与预览

Synthetic Python coverage includes bounded parallel discovery, zero/one/multiple
matches, scope validation, timeout/fingerprint handling, lock/cooldown, same-origin
POST checks, monitor eligibility, stale receipts, atomic/idempotent saves and preserved
old mappings. Archive integration verifies same-ID rebinding, replay exclusion,
unchanged old samples/daily totals/incidents and first-sample shared history activation.

Cached Chromium acceptance (`tests/test_endpoint_b_browser.js`) exercises all user
states at 1440, 768, 390 and 320 pixels, verifies preselection, save gating, one scan
per click sequence, shared card/curve address and no horizontal overflow. These are
synthetic Chromium checks, not a claim of actual iOS 9 Safari or live deployment testing.

```sh
python -B -m unittest discover -s tests -v
NETWORK_BROWSER_PYTHON=<python-with-requirements> node tests/test_endpoint_b_browser.js
```

The `endpoint-b-browser` GitHub Actions job uploads screenshots and its acceptance
report as **endpoint-b-desktop-mobile**. Images contain RFC5737 synthetic addresses
only. The development sandbox blocks Chromium startup system calls; browser acceptance
must run in CI or on a host permitting Chromium, independently of local unit tests.

在 PR 的 Actions 中打开 `endpoint-b-browser`，下载 **endpoint-b-desktop-mobile**，
可查看四种宽度的“等待 Beszel”与“映射生效”效果图及验收报告。当前开发沙箱限制 Chromium
启动系统调用，因此浏览器验收交由 CI；截图只含 RFC5737 合成地址。
