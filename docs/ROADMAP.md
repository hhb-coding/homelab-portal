# HomeLab Portal — Unified Development Roadmap / 统一开发路线图

**Original planning date / 初版规划日期:** 2026-10-13  
**Repository:** `hhb-coding/homelab-portal`  
**Status / 状态:** Maintained in GitHub `main` since PR #10 (2026-10-14); documentation consistency review 2026-10-19 / 已合并至 `main` 并持续维护，最近核对 2026-10-19  
**Approved scopes / 已批准范围:** [Step 7.03 Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11) and [Step 7.05 Security Events](step-7-05-security-events.md)

> Scope numbering: `Step 7.05` is an **internal work-package identifier**, not a claim that GitHub tag/release `v7.05` exists. The repository has already published [v0.2.0](https://github.com/hhb-coding/homelab-portal/releases/tag/v0.2.0). Never equate a planned Step with a deployed version.
>
>
> 编号说明：`Step 7.05` 是内部开发任务编号，不代表 GitHub 已发布名为 `v7.05` 的 Tag 或 Release。GitHub 已正式发布 `v0.2.0`。规划、已合并代码与生产运行状态必须分开核对。

## 1. Version and scope decisions / 编号及范围决议

**Decision (2026-10-13):** Reserve **Step 7.05 for Security Events**, matching the separately approved requirements. The earlier conversational idea called “Step 7.05 Long-term History Dashboard” was **not an implemented/merged release**; move it to **Step 7.06**. No scope is dropped. Security Events is **approved for future development only**; no source implementation, Issue, PR, merge, deployment or production change is implied by this document.

**决议：**保留 **Step 7.05 Security Events** 的已批准需求；此前聊天中暂拟为 7.05 的“长期历史查询页面”移至 **Step 7.06**，两者都保留。不将“需求批准”误写为“已实现、已合并或已上线”。

| Step | Description / 功能 | Evidence-based status / 有证据的状态 | Dependency / 关联 |
| --- | --- | --- | --- |
| 1–6 | Flask/SQLite, Heartbeat, Beszel, Device/Network/Lite, GitHub docs/CI | Implemented on GitHub / GitHub 已有实现 | Existing base |
| 7.01 | Local Linux CPU Temp/Freq in Full Detail | Merged in PR #7; deployment previously reported, reverify HP / PR #7 已合并，HP 状态需现场核实 | Existing Portal API |
| 7.02 | Temp/Freq in Lite | Merged in PR #8; deployment previously reported, reverify HP / PR #8 已合并，HP 状态需现场核实 | 7.01 |
| 7.03 | **Cross-platform CPU Frequency Collection** — HP Linux + Dell Linux + ThinkPad X230 Windows; ~1-minute sampling / 跨平台 CPU 主频采集 | **Approved scope in [Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11); not implemented / 需求已批准，未开发** | Reuse/extend Step 7.04 performance history architecture; unified storage for Step 7.06; no X230-only history system |
| 7.04 | Beszel 1-minute metrics archive, separate 180-day SQLite, 1TB HDD guard and 5-minute timer | **Merged PR #9** (`d776e7e`); production timer/data still require direct HP verification / GitHub 已合并，HP 运行实况待核 | Beszel Hub |
| **7.05** | **Security Events: Caddy-authenticated Portal requests, HTTP 401 and anomalies** | **Approved plan, not implemented / 已批准但未开发** | Caddy JSON access log; independent SQLite/timer |
| **7.06** | **Long-term History Dashboard: query archived performance data (24h/7d/30d/custom)** | **Proposed, not implemented / 原 7.05 提议顺延，未开发** | 7.04 archive storage |
| 8.x | Network Monitoring: Gateway, Internet, DNS, LAN, ZeroTier latency/loss/recovery | Proposed / 待开发 | Existing Network tab |
| 9.x | Service Monitoring: Portal, Beszel, qBittorrent, Samba, VM/Docker status | Proposed / 待开发 | Service API/status checks |
| 10.x | General Event/Alert: device, IP, CPU/RAM/temp, service alerts, later notifications | Proposed / 待开发 | Historical/network/service data |
| 11.x | Automation/DevOps: Ansible, client rollout, config/systemd and CI | Proposed / 待开发 | Stable deployment design |
| 12.x | Documentation/Portfolio/release readiness, eventual v1.0.0 target | Proposed / 待开发 | Prior Steps |

Historical snapshot (2026-10-13): PR #7, #8 and #9 were merged while this ROADMAP was still being prepared; PR #10 subsequently merged the document. By 2026-10-19, Step 7.03 was expanded and linked to Issue #11. **Repository merges do not establish actual HP deployment, timer or archive health; verify those separately on the host.**

历史快照：2026-10-13 时 PR #7–#9 已合并，而路线图尚在准备；之后 PR #10 已正式合并。至 10 月 19 日，Step 7.03 已扩大范围并引用 Issue #11。GitHub 合并不等于 HP 实际部署状态。

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

- **8.x Network Monitoring:** gateway/ISP/Internet/DNS reachability, periodic Ping, jitter/loss/latency, ZeroTier status, outage/recovery history and multi-target diagnosis. The existing Network tab is only an address/status summary, not an active scanner.
- **9.x Services:** Beszel, Portal, Samba, qBittorrent availability, download/upload/DHT indicators and later VM/Docker/SMART checks. DHT=0 alone must not trigger an unconditional restart.
- **10.x Alerts:** IP/device changes, sustained CPU/RAM/temperature events and service down/recovery; start with persistent events and UI, evaluate email later as separate scope.
- **11.x Automation:** Ansible-driven Heartbeat/agent/service/config deployment and GitHub Actions validation.
- **12.x Release/Portfolio:** screenshots, bilingual README, architecture/API/security/compatibility docs, repeatable installation and release readiness.

## 6. Coordination rule / 跨 Project 同步

This roadmap and the approved Step 7.05 scope document should be referenced in future ChatGPT Project / Codex work. **Separate Projects do not inherently synchronize their task plans.** GitHub repository documentation, after merger into `main`, is the shared planning record. The **latest HP checked-out code and running service** remain authoritative for actual deployment state.

本文件与 7.05 专项需求须在各 Project 的后续开发对话中明确引用。不同 ChatGPT Project 的聊天记忆不能当作自动同步的唯一依据。文档合并后以 GitHub 仓库为统一需求规划记录，实际部署事实仍以 HP 机器为准。
