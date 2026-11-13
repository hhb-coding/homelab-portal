# HomeLab Portal — Unified Development Roadmap / 统一开发路线图

**Original planning date / 初版规划日期:** 2026-10-13  
**Repository:** `hhb-coding/homelab-portal`

**Status / 状态** — Maintained in GitHub `main`. Step 8 HP acceptance recorded on
2026-11-13. / 已在 `main` 维护，2026-11-13 记录 Step 8 的 HP 验收状态。

**Approved scopes / 已批准范围:** [Step 7.03 Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11) and [Step 7.05 Security Events](step-7-05-security-events.md)

> Scope numbering: `Step 7.05` is an **internal work-package identifier**, not a claim that GitHub tag/release `v7.05` exists. The repository has already published [v0.2.0](https://github.com/hhb-coding/homelab-portal/releases/tag/v0.2.0). Never equate a planned Step with a deployed version.
>
>
> 编号说明：`Step 7.05` 是内部开发任务编号，不代表 GitHub 已发布名为 `v7.05` 的 Tag 或 Release。GitHub 已正式发布 `v0.2.0`。规划、已合并代码与生产运行状态必须分开核对。
>
> **HP production snapshot / HP 生产验收快照（2026-11-13）.** The operator
> deployed `44e4bfcb51064a39018937f9948af57ab232e6a7` (PR #31) with local patches.
> Live acceptance passed for the network quality layout, Endpoint B discovery
> and mapping, fresh archive samples, CPU history and Web health.
> [Acceptance record](network-quality-layout-acceptance.md#hp-production-acceptance)
>
> HP 已部署 PR #31 合并提交并保留本机补丁。网络质量布局、Endpoint B 发现和映射、
> 归档新样本、CPU 历史及 Web 健康均通过实机验收。
>
> **Earlier HP snapshot / HP 历史验收快照（2026-11-05）.** The operator accepted
> the Step 7.07.1 Device and History views at `5808ffadeee4f34c8e0092ca5768b8037e8617e3`
> (PR #22). 当日已确认 HP 上的 Step 7.07.1 Device 与 History 图表。

## 1. Version and scope decisions / 编号及范围决议

**Decision (2026-10-13):** Reserve **Step 7.05 for Security Events**, matching the separately approved requirements. The earlier conversational idea called “Step 7.05 Long-term History Dashboard” was **not an implemented/merged release**; move it to **Step 7.06**. No scope is dropped. Security Events is **approved for future development only**; no source implementation, Issue, PR, merge, deployment or production change is implied by this document.

**决议：**保留 **Step 7.05 Security Events** 的已批准需求；此前聊天中暂拟为 7.05 的“长期历史查询页面”移至 **Step 7.06**，两者都保留。不将“需求批准”误写为“已实现、已合并或已上线”。

| Step | Description / 功能 | Evidence-based status / 有证据的状态 | Dependency / 关联 |
| --- | --- | --- | --- |
| 1–6 | Flask/SQLite, Heartbeat, Beszel, Device/Network/Lite, GitHub docs/CI | Implemented on GitHub / GitHub 已有实现 | Existing base |
| 7.01 | Local Linux CPU Temp/Freq in Full Detail | **Merged PR #7; HP production user-accepted / 已合并且 HP 实机确认** | Existing Portal API |
| 7.02 | Temp/Freq in Lite | **Merged PR #8; HP production user-accepted / 已合并且 HP 实机确认** | 7.01 |
| 7.03 | **Cross-platform CPU Frequency Collection** — HP Linux and X230 Windows; Dell pending / 跨平台 CPU 主频采集 | **HP + X230 deployed and working / HP、X230 已部署并验收；Dell 系统重装后待处理**; [Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11), [design](cpu-frequency.md). Do not describe Dell collection as deployed. | Unified Step 7.04 history schema; no X230-only history system |
| 7.04 | Beszel 1-minute metrics archive, separate 180-day SQLite, 1TB HDD guard and 5-minute timer | **HP deployed and operator-verified / HP 已部署并验收**; incremental collection to separate HDD SQLite. Historical implementation [PR #9](https://github.com/hhb-coding/homelab-portal/pull/9). | Beszel Hub |
| **7.05** | **Security Events: Caddy-authenticated Portal requests, HTTP 401 and anomalies** | **Approved plan, not implemented / 已批准但未开发**; explicitly deferred | Caddy JSON access log; independent SQLite/timer |
| **7.06–7.06.3.1** | **Archive-backed History Dashboard** — Local custom range, three CPU metrics, refresh/source times, DST handling, occurrence CSS fix | **Merged PRs #16–#20; deployed and operator-accepted 2026-11-05 / 已合并、部署、验收**; [details](step-7-06-history.md) | Step 7.04 Schema v2 archive |
| **7.07–7.07.1** | **Expanded History and Device axes** — History six full-width rows (seven series), Device three CPU charts with left Y ticks | **Merged [PR #21](https://github.com/hhb-coding/homelab-portal/pull/21) + [PR #22](https://github.com/hhb-coding/homelab-portal/pull/22); HP deployed, visual checks accepted / 已合并、部署并人工确认**; [details](step-7-07-expanded-history.md) | Read-only extension of 7.04 archive; no schema or agent changes |
| 8.01 | Network monitor/API read-only verification | Six 10-second ICMP targets verified / 已只读核验 | Baseline `7a21774` |
| 8.02 | API-only network minute archive, durable daily totals and outage/recovery events | [PR #25](https://github.com/hhb-coding/homelab-portal/pull/25) merged. **HP deployed and accepted 2026-11-11 / 已部署并验收**. v3, backup/restore, six-role sync and first timer run verified. [Archive contract](step-8-02-network-archive.md) | Explicit v3 migration; existing 7.04 HDD/timer |
| 8.03 | Archive-backed latency/loss charts including both public targets and persisted events | [PR #26](https://github.com/hhb-coding/homelab-portal/pull/26) merged. Included in the accepted HP snapshot / 已合并，纳入 HP 已验收版本 | Step 8.02 v3 network archive |
| 8.03.1 | Full-row private/public RTT, fixed role identity and inspectable loss records | [PR #27](https://github.com/hhb-coding/homelab-portal/pull/27) merged. **HP deployed and accepted 2026-11-12 / 已部署并验收**. [Validation](step-8-03-1-network-readability.md) | Existing v3 archive/read-only route |
| 8.03.2 | Compact Network device cards, online uptime and independent status/uptime/Heartbeat ordering | [PR #28](https://github.com/hhb-coding/homelab-portal/pull/28) merged. **HP deployed and accepted 2026-11-12 / 已部署并验收**. [Validation](step-8-03-2-network-device-cards.md) | Deployed 8.03.1 baseline `2d65388`; existing dashboard API |
| 8.03.3 | Seven network ranges and per-chart weighted statistics with temporary preview and pinned targets | [PR #29](https://github.com/hhb-coding/homelab-portal/pull/29) merged. **HP deployed and accepted 2026-11-12 / 已部署并验收**. [Validation](step-8-03-3-network-range-stats.md) | Deployed 8.03.2 baseline `046be3f`; existing read-only network API/archive |
| 8.03 follow-up / 扩展 | Endpoint B TP-Link discovery, local mapping and archive sync / 查找、映射与归档同步 | [PR #30](https://github.com/hhb-coding/homelab-portal/pull/30) merged. **HP live acceptance passed with PR #31 on 2026-11-13 / 随 PR #31 部署并通过实机验收**. [Workflow](network-endpoint-b-discovery.md) | Existing HP ICMP probe in Beszel |
| 8.03 follow-up / 扩展 | Network quality 3 / 1 / 2 layout and deployment acceptance fixes / 卡片布局与验收修复 | [PR #31](https://github.com/hhb-coding/homelab-portal/pull/31) merged. **HP deployed and accepted 2026-11-13 / 已部署并验收**. [Acceptance](network-quality-layout-acceptance.md#hp-production-acceptance) | PR #30 and the existing archive timer |
| 9.x | Service Monitoring: Portal, Beszel, qBittorrent, Samba, VM/Docker status | Proposed / 待开发 | Service API/status checks |
| 10.x | General Event/Alert: device, IP, CPU/RAM/temp, service alerts, later notifications | Proposed / 待开发 | Historical/network/service data |
| 11.x | Automation/DevOps: Ansible, client rollout, config/systemd and CI | Proposed / 待开发 | Stable deployment design |
| 12.x | Documentation/Portfolio/release readiness, eventual v1.0.0 target | Proposed / 待开发 | Prior Steps |

Historical snapshot (2026-10-13): PR #7, #8 and #9 were merged while this ROADMAP was still being prepared; PR #10 subsequently merged the document. By 2026-10-19, Step 7.03 was expanded and linked to Issue #11. **Those were historical merge/development statuses, superseded by the operator-confirmed 2026-11-05 snapshot above. Repository merges alone never prove HP health; verify the live host before operations.**

历史快照：2026-10-13 时 PR #7–#9 已合并，而路线图尚在准备；之后 PR #10 已正式合并。至 10 月 19 日，Step 7.03 已扩大范围并引用 Issue #11。上述为历史进度；2026-11-05 的操作员验收记录见上方，不能仅凭 GitHub 合并推断运行状况。

## 2. Approved Step 7.05 — Security Events / 已批准范围

**Source of truth for this feature:** [step-7-05-security-events.md](step-7-05-security-events.md) (cross-Project approved plan). Do not shorten the scope to a generic login counter.

- UI: Add **Events** beside Device / Network; show rolling **24 h / 7 d / 30 d** rows and statistics update time plus partial-coverage warnings.
- Per row: **authenticated GET `/` requests** (approximate successful home-page accesses, **not precise login sessions**); **HTTP 401 authentication rejections** (includes first credential challenge; **not equivalent to wrong-password attempts**); **deduplicated abnormal incident counts**.
- Ingestion: **Caddy JSON Access Log → 5-minute Python incremental one-shot → dedicated SQLite event/summary database → aggregate-only Flask `/api/events` → Events tab**. Dedicated systemd timer; **no new resident Web server**.
- Data: retain the minimum useful events/aggregates for **90 days**; do not ingest every successful 5-second polling request. Handle log rotation/truncation, checkpoints, restarts, duplicate events, atomic commits, missing/corrupted database and retention.
- Default configurable incident thresholds: **at least 20 HTTP 401 within 5 minutes** OR **at least 100 HTTP 401 within 1 hour**, with overlapping-window and ongoing-incident deduplication. Specify exact count semantics in implementation and tests.
- Security: only **Caddy-fronted Portal** requests; **Beszel direct Tunnel traffic is excluded**. Keep **Cloudflare Named Tunnel → Caddy Basic Auth → Portal** unchanged. Do **not** infer trusted client IP or a single attacker before proxy/IP trust is verified.
- Out of scope: precise login-session count, automated blocking, rate limiting, email alerts, cross-service/Beszel logs, visitor-IP analytics.
- Compatibility: preserve existing ES5/XHR and legacy iOS 9 Safari, with Device/Network/Events navigation and synthetic-log tests. No raw IPs, Authorization/Cookies, credentials, hashes, real access logs or production SQLite in API/GitHub.

## 3. Step 7.04 versus 7.05 versus 7.06 / 避免实现冲突

| Area | 7.04 Metrics Archive | 7.05 Security Events | 7.06 History Dashboard |
| --- | --- | --- | --- |
| Source | Beszel minute `system_stats` | Caddy JSON access log | 7.04 archive |
| Task | Existing metrics archive timer | Separate **security** collector timer | On-demand Flask read/query |
| Storage | Dedicated metrics SQLite on verified HDD mount; 180-day retention | **Different** dedicated SQLite event/aggregate store; 90-day retention | Read metrics SQLite; avoid modifying 7.04 raw metrics |
| User interface | No archive-backed UI in 7.04 baseline | New **Events** tab | Long-range charts/filter/statistics in Device/history area |
| Meaning | Performance samples | Authentication/HTTP security observations | Historical performance analytics |

- The two five-minute timers **may coexist** but must have distinct names, checkpoints, file paths, lock files, schema and retention; do not repurpose or attach the security parser to the Beszel collector.
- A common scheduling cadence does not imply a shared database or shared transaction.
- Step 7.05 need not wait for 7.06: it uses Caddy logs. Step 7.06 does not require Caddy events: it reads the archived metrics.
- Step 10 is a future *general event/alert framework*; recording security anomalies in 7.05 does not authorize email/push, IP blocking or automatic mitigation.
- Acknowledge that Caddy access log HTTP 401 may include normal browser Basic Auth challenges; distinguish HTTP status counts from guesses about password mistakes or human sessions.

## 4. Development gates / 开发前检查与安全门槛

1. On HP inspect **production and development** directories independently: actual commit/branch, `git status`, local changes, current work, active timers and deployed version. GitHub `main` may lag; **do not overwrite or reset local changes**.
2. Review existing `.env`/Caddy configuration **locally only**; do not export secrets or real logs into ChatGPT/GitHub. Confirm whether Caddy JSON logging is actually enabled, its fields, Basic Auth response behavior and rotation before designing the parser.
3. Start a **separate feature branch** for 7.05 from the appropriate reconciled base; work only in development checkout. No production edits, timer activation, restart or deployment without later review/authorization.
4. Include bilingual docs/comments, public-safe examples, SQLite integrity/retention/rotation/replay tests, overlapping incident tests, `GET /` vs `/api/*` counting tests, iOS 9 ES5/XHR regression and rollback guidance.
5. Distinguish: **approved requirement → code developed → PR reviewed/merged → deployed → observed/verified**. Mark statuses independently.

## 5. Other planned streams / 其他规划

- **8.x network follow-ups / 网络后续规划** — DNS resolution probes, dedicated
  ZeroTier path probes, jitter statistics and more detailed multi-target
  diagnostics, including X230 dual-path comparison. / DNS 解析探测、ZeroTier
  路径探测、抖动统计及更细的多目标诊断（含 X230 双路径对照）。
- **9.x Services:** Beszel, Portal, Samba, qBittorrent availability, download/upload/DHT indicators and later VM/Docker/SMART checks. DHT=0 alone must not trigger an unconditional restart.
- **10.x Alerts:** IP/device changes, sustained CPU/RAM/temperature events and service down/recovery; start with persistent events and UI, evaluate email later as separate scope.
- **11.x Automation:** Ansible-driven Heartbeat/agent/service/config deployment and GitHub Actions validation.
- **12.x Release/Portfolio:** screenshots, bilingual README, architecture/API/security/compatibility docs, repeatable installation and release readiness.

## 6. Coordination rule / 跨 Project 同步

This roadmap and the approved Step 7.05 scope document should be referenced in future ChatGPT Project / Codex work. **Separate Projects do not inherently synchronize their task plans.** GitHub repository documentation, after merger into `main`, is the shared planning record. The **latest HP checked-out code and running service** remain authoritative for actual deployment state.

本文件与 7.05 专项需求须在各 Project 的后续开发对话中明确引用。不同 ChatGPT Project 的聊天记忆不能当作自动同步的唯一依据。文档合并后以 GitHub 仓库为统一需求规划记录，实际部署事实仍以 HP 机器为准。
