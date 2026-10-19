# Changelog / 更新日志

This changelog distinguishes published releases from subsequent development on `main`; internal Step numbers are not semantic version tags.
本日志区分正式发布与主分支后续工作。Step 7.03 等内部编号不等于软件版本号。

## Unreleased changes on `main` after v0.2.0 / v0.2.0 之后的未发布变更

- **Step 7.01 (PR #7, 2026-10-12):** local Linux CPU frequency alongside temperature in Full Device Detail. / Full 本机 CPU 主频显示。
- **Step 7.02 (PR #8, 2026-10-12):** Temp/Freq in Lite View. / Lite 温度与频率。
- **Step 7.04 (PR #9, 2026-10-12):** independent Beszel one-minute archive collector, separate SQLite, 180-day retention, HDD UUID safety checks and optional systemd timer templates. Existing charts still read Beszel. Repository merge does not prove deployment on any host. / 分钟级性能历史归档代码已合并，部署状态须现场确认。
- **Planning documents (PR #10, 2026-10-14; later roadmap update):** unified [ROADMAP](docs/ROADMAP.md), approved Step 7.05 Security Events plan, and expanded [Step 7.03 Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11) for ~1-minute HP Linux / Dell Linux / X230 Windows CPU frequency, aligned with Step 7.04 storage and future Step 7.06 charts. **Steps 7.03, 7.05 and 7.06 remain plans, not implementations.** / 跨平台频率、安全事件和历史展示规划已登记，但尚未开发。

These entries have not been published as another GitHub Release. / 上述更新不代表已有新的正式 Release。

## v0.2.0 — published 2026-10-10 / 已于 2026-10-10 发布

Published [GitHub Release v0.2.0](https://github.com/hhb-coding/homelab-portal/releases/tag/v0.2.0), immutable tag commit `d3843420bd7d99925b086b9bda6faf1cfbf29a29`.
正式版本以该 Tag 为准，不将 10 月 12 日之后合并的功能倒写入 v0.2.0。

- Device UI V3, capacity-aware Mini Cards and Details, better offline Last seen presentation. / 卡片、设备详情、容量展示和离线心跳显示优化。
- Full/Lite improvements, Network tab layout, source-staleness warning and ES5/legacy-browser support. / Full/Lite、Network、过期数据警告和旧版浏览器兼容性。
- Flask/SQLite, Linux and Windows Heartbeat clients, Beszel metrics/history, bilingual docs and GitHub Actions smoke tests. / Flask/SQLite、跨平台心跳、Beszel 指标及历史、双语说明和 CI。
- Published release notes document successful Lite/Full iPad mini 1 Safari iOS 9.1.3 testing; these findings do not certify later code. / 发布说明中的旧 iPad 实测不代表之后版本通过真机测试。

**Published v0.1.0 Release erratum / 已发布 v0.1.0 说明勘误：**
Its [Release description](https://github.com/hhb-coding/homelab-portal/releases/tag/v0.1.0) calls Beszel integration a future enhancement, but its immutable tag already contains `beszel_client.py` and describes Beszel integration in the tagged README. That sentence is inaccurate for the tagged code. This documentation update does not edit the published GitHub Release body or rewrite an immutable tag.
已发布的 v0.1.0 说明误把 Beszel 集成写成未来工作，与该 Tag 的已有源码和 README 不一致；此处记录勘误，不修改 Tag 或已发布 Release 正文。

## v0.1.0 — published 2026-10-09 / 已于 2026-10-09 发布

Historical preparation baseline: `f261de40280dfd9cbd57a1c9ef24bf83e4fbd347`. The actual published [v0.1.0 release](https://github.com/hhb-coding/homelab-portal/releases/tag/v0.1.0) refers to tag commit `bd4892b4d419198891e3cab7eab9627f9bd5ff25`. The following test counts and notes describe the preparation snapshot, not the current `main`.
历史准备基线与正式发布 Tag 不同；以下清单与测试数字保留当时的验收记录，并非目前 `main` 的结果。

### Included / 已实现

- Flask/SQLite device registry, token-authenticated Heartbeat and independent
  LAN/ZeroTier IP-change records. / 设备登记、心跳鉴权及独立地址变更记录。
- Linux Python and Windows PowerShell clients; example Linux systemd scheduling
  and Windows configuration. / 跨平台客户端及 Linux 定时器示例。
- Beszel metrics and one-to-one device linking with `beszel_system_id`.
  / Beszel 指标与唯一设备关联。
- Full Device view with Mini Cards, selected details, browser-local live SVG
  trends and persistent Beszel history. / 完整设备视图、详情及两种 SVG 趋势。
- Stage 6-C: `/lite`, five-second ES5/XHR refresh, no history or chart loading,
  reciprocal Full/Lite links and CI smoke tests. / 轻量视图与双向导航、CI 测试。
- Stage 6-D: Network tab with totals, online/offline/unknown counts, reported
  LAN/ZeroTier addresses and last Heartbeat. / 网络信息汇总标签。
- Stage 6-E: consistent colors/spacing, responsive wrapping, unknown-state
  display, missing-number handling and malformed-record isolation.
  / 界面一致性、换行布局、未知/缺失数据及无效条目处理。
- 8 Flask/static tests, 21 Lite assertions and 45 Full/Network assertions.
  / 自动化测试覆盖上述功能及异常状态。

### Release documentation / 发布文档

- English-first bilingual installation, configuration, API and security guide.
  / 英文在前的双语安装、配置、API 与安全说明。
- Draft release notes, release checklist and retained browser validation checklist.
  / 发布说明草稿、发布前与浏览器验收清单。
- Safer blank server Heartbeat-token example and expanded local-artifact ignore rules.
  / 服务端 Token 示例留空、补充本地文件忽略规则。

- Maintainer-approved [MIT License](LICENSE), Copyright (c) 2026 Hongbin He.
  / 维护者已确认 MIT 许可证及版权署名。

### Known limitations / 已知限制

- Prior Full-page iOS 9 Safari testing is known; Lite, new Network and 6-E
  real-device validation are still pending. / 历史 Full 实测不代表新版验收通过。
- Network summarizes reports; it performs no scan, ping or topology discovery.
  / Network 不是扫描器、Ping 检测或自动拓扑。
- Read APIs have no Portal login; Flask's built-in server is not a hardened
  public deployment. / 读取无内置登录，服务未做公网加固。
- Strict optional Heartbeat field validation and comprehensive Beszel-version
  compatibility coverage are not implemented. / 严格字段校验与版本兼容覆盖待完善。
- Historical `minutes` limits sample count, not elapsed time; some transport
  errors can yield HTTP 500. / 历史参数限制样本数，部分传输异常可返回 500。

Older preparation notes above are preserved for traceability. For current behavior see the README and the tagged Release notes. / 原始准备记录作为历史留存，现状以 README 与正式 Tag 为准。
