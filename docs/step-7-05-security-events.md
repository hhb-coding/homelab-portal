# HomeLab Portal Step 7.05 — Security Events（已确认需求 / Approved Plan）

**Status:** 已批准的规划（approved scope）；2026-10-14 完成 Caddy JSON 日志格式、轮换与访问权限的只读开发前检查（Phase 0）；**Phase A–C 尚未开始实现、未部署**。
**Project:** `hhb-coding/homelab-portal`
**Coordination:** 这份文件可放入 GitHub 仓库 `docs/`，并在其他 ChatGPT Project / Codex 对话中引用；真正的权威基线始终是 HP 机器上的最新 Git 工作树与生产部署状态。

> **Naming:** “Step 7.05” is an internal work package, not a GitHub `v7.05` Release. The actual latest published release is [v0.2.0](https://github.com/hhb-coding/homelab-portal/releases/tag/v0.2.0). The Phase 0 log check did not install a collector or modify Caddy. The least-privilege log-reader access design remains pending.
>
> **命名与进度：**Step 7.05 是内部开发编号，不是正式的 v7.05 发布。Phase 0 仅检查现有日志，未安装采集器；未来需要解决日志只读授权及轮换兼容性。

## 0. 开发前必须核对

- 目前 HP 上的生产 Portal 约为 v7.04；已有独立的生产目录和开发目录。**开发前必须实际核对**部署版本、分支、`git status`、当前进行中的任务和现有路线图；GitHub `main` 可能落后于部署版本。
- 新建独立 feature branch；不要直接修改生产目录；未经评审不要执行生产重启、部署、覆盖或强制清理。
- 代码、README、配置范例和测试保持公开仓库发布安全；不可提交真实 IP、域名、账号、密钥、密码哈希、访问日志或本地路径等环境敏感信息。

## 1. UI 要求（已确定）

- 在当前 `Device` / `Network` 同级增加 `Events` 标签，位置对应现有标签栏右侧空白区域。
- 点击 `Events` 展示三行滚动时间窗口：**过去 24 小时、过去 7 天、过去 30 天**。
- 每行包含：
  1. **已认证首页访问**（Authenticated home-page requests）：只用于估算成功打开 Portal 首页的次数，**不能命名为精确登录次数**。每五秒的 API 轮询不能算一次登录。
  2. **认证拒绝（HTTP 401）**：首次无凭据挑战也会生成 401，**不能等同于错误密码输入次数**。
  3. **异常事件数**：按定义的时间阈值判定并去重的异常时段/事件次数。
- 显示统计更新时间和数据覆盖情况。新采集不足 7/30 天时要明确标记“数据不足/部分覆盖”，不可呈现为完整历史。
- 保留现有轻量页面风格、ES5 / XMLHttpRequest 编写方式及 iOS 9 Safari 兼容要求；中英文代码注释和文档。

## 2. 采集与存储（已确定）

- 采集链路：Caddy JSON Access Log → Python 增量解析 → 独立 SQLite 统计/事件数据库 → Flask `/api/events` → Events Tab。
- systemd timer 每 5 分钟运行一次，**无新常驻 Web 服务**。
- 正确处理文件轮换、截断、重启、断点恢复、重复采集、原子提交、数据库损坏/不可读等场景。
- 保留 **90 天**可满足 30 天滚动统计的必要数据或事件汇总；不要盲目复制 Portal 每 5 秒刷新产生的所有 200 日志。
- 仅统计**经过 Caddy 的 Portal 请求**；Beszel 目前直接通过 Tunnel 到它自己的认证服务，**不包含在 v7.05 的日志分析范围**。

## 3. 事件定义（已确定的第一版阈值）

- HTTP 401 作为“认证拒绝次数”。
- 每 **5 分钟 ≥ 20 次 401** 或每 **1 小时 ≥ 100 次 401**，触发异常规则。
- 应明确说明“异常事件”的计数口径，并对重叠窗口去重，避免连续 5 分钟重复记录同一次持续异常。
- 阈值要可配置；第一版只记录、显示，不自动封锁来源。
- 当前可信真实访客 IP 的识别尚待验证。**在验证前不推出任何声称来源 IP 或单一攻击者的统计**。

## 4. 安全要求

- 不更改现有 Cloudflare Named Tunnel → Caddy Basic Auth → Portal 链路，外网入口继续由 Caddy 认证保护。
- `/api/events` 只提供聚合数据。不得输出原始 IP、密码、Authorization、Cookie、凭据文件内容或原始日志。
- 不把日志或生产 SQLite 数据提交到 GitHub。
- Cloudflare Rate Limiting、自动邮件告警、精确会话登录统计、登录封禁、Beszel 统一日志收集**不属于 v7.05 第一版范围**。

## 5. 验收

1. Device / Network / Events 切换正常，旧 iPad 浏览器可用。
2. `24h / 7d / 30d` 的事件数据有明确时间边界和覆盖率标注。
3. 回归测试覆盖：首次 401 challenge、输入错误凭据产生的 401、已认证 GET `/`、后台 `/api/*` 轮询、日志轮换、断点重采、时间窗口边界、异常事件去重。
4. `systemd timer` 运行正常；SQLite 完整性和历史裁剪通过。
5. README / CHANGELOG / 测试更新齐全；独立开发与 PR 审查后才部署；保留回滚方案。

## 6. 跨 ChatGPT Project / Codex 协同规则

- 在「Win电脑升级和学习」Project 中继续开发前，**明确把本文件作为 v7.05 已批准需求输入**，先核对该 Project 已规划/正在进行的版本范围是否冲突。
- **不假设不同 Project 的聊天记忆一定自动同步**；不能仅凭 ChatGPT 的记忆声称其它会话已获知或采纳 v7.05。
- 如 v7.05 已被其他工作预定，请先解决编号冲突，不要强行覆盖原计划；必要时将本功能改为后续空闲版本，并更新唯一的仓库规划记录。
- 此文件记录的是**规划批准**，不代表代码已经提交、PR 已合并、GitHub Issue 已创建或功能已上线。
