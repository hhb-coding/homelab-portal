# v0.1.0 release checklist / 发布前检查

This is a preparation checklist, not evidence of a published release. Leave
items unchecked until verified for the actual release candidate.
这是发布准备清单，不是已发布证明；候选版本未确认的项目保持未勾选。

- [x] Maintainer approved the [MIT License](../LICENSE); the root LICENSE and
  bilingual README reflect Copyright (c) 2026 Hongbin He.
  / 维护者已确认 MIT，根目录 LICENSE 与双语 README 已更新。
- [ ] Review/merge the documentation branch through the maintainer's chosen
  process and select the final immutable release commit (including docs).
  / 按维护者流程审核文档分支，选定包含文档的最终发布 Commit。
- [ ] Recheck tracked files and relevant history for real secrets, personal
  identifiers, runtime data and private screenshots. If a real historical
  secret is found, stop and arrange rotation/remediation; do not silently rewrite history.
  / 复查文件与历史；真实密钥泄露需停止并处理，不自行重写历史。
- [ ] Confirm local smoke tests, frontend tests and GitHub Smoke tests all pass
  on the final release commit. / 最终版本本地测试与 GitHub CI 全部通过。
- [ ] Verify installation from a fresh checkout with private configuration,
  a temporary database and no existing production service. Include both clients
  and Beszel linking, documenting versions tested. / 新目录验证安装及客户端与 Beszel 关联。
  Core fresh-clone acceptance is recorded in [installation validation](installation-validation.md);
  live clients/Beszel and service installation remain pending, so this item stays unchecked.
  / 核心新安装检查已记录，真实客户端、Beszel 与服务安装未完成，整体项目不勾选通过。
- [ ] Execute the [browser checklist](legacy-browser-validation.md), including
  real iOS 9 Safari for Lite/Network, or explicitly retain the unverified limitation.
  / 完成浏览器验收，未实测时如实保留限制说明。
- [ ] Review bilingual changelog/release notes, installation revision and optional
  sanitized screenshots. / 核对双语发布说明、安装版本和可选脱敏截图。
- [ ] Obtain separate authorization to create the `v0.1.0` tag and publish the
  GitHub Release at the approved commit. **Neither is authorized by this prep.**
  / 另行授权创建 Tag 与正式 Release，本次准备不包含发布操作。

Confirmed license / 已确认许可证：[MIT License](../LICENSE).
Copyright (c) 2026 Hongbin He.
