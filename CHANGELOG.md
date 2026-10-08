# Changelog / 更新日志

## v0.1.0 — release candidate, not yet released / 发布准备，尚未发布

Application baseline: `f261de40280dfd9cbd57a1c9ef24bf83e4fbd347`.
No release date, version tag or GitHub Release is asserted here.
应用基线如上；本文件不宣称已经发布，不填写未确认的发布日期。

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

### Known limitations / 已知限制

- License decision is pending. / 许可证待决定。
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

No earlier release versions are invented. / 不编造此前发布版本。
