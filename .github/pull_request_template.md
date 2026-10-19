<!-- HomeLab Portal PR checklist / PR 审核检查模板 -->
## Summary / 修改摘要

<!-- What changed? Which Issue and Step does this serve? / 修改什么，关联什么 Issue/Step？ -->

Closes / Related Issue: <!-- #... or N/A -->
Step / 任务编号: <!-- Step 7.xx / N/A -->

## Scope and status / 修改范围与状态

- [ ] This PR changes only the files described here. / 已确认实际修改范围。
- [ ] This is implementation, documentation, or tests—not a declaration of production deployment. / 区分代码变更与生产部署。
- [ ] The ROADMAP and applicable Issue are consistent, where scope or status changed. / 涉及需求或进度变化时已核对路线图与 Issue。
- [ ] Published Tag/Release history is not silently rewritten. / 不静默改写已发布的历史版本。

## Testing evidence / 测试证据

<!-- State what actually ran, its outcome, and what was NOT verified. / 写出确实运行的测试、结果和尚未验证的项目。 -->

- [ ] GitHub Actions **Smoke tests / test** completed successfully (or explain why unavailable).
- [ ] Relevant Python/Node tests and static syntax checks passed (or not applicable with reason).
- [ ] Changes involving UI preserve Full/Lite and legacy ES5/XHR compatibility, or explicitly document the exception.
- [ ] Hardware/browser/production tests are not claimed unless actually performed.

## Security and operations / 安全与运维边界

- [ ] No real IPs, private endpoints, usernames, credentials, tokens, hashes, log data, database snapshots or production backups in commits or PR content.
- [ ] Production and development trees were identified separately when host changes are involved; no unknown worktree was reset.
- [ ] For changes touching storage, background jobs, services or APIs: migration, retention, error handling and rollback are described.
- [ ] No production deployment, service restart, systemd timer installation or DB migration was executed without separate approval.
- [ ] Documentation and comments are bilingual where appropriate.

## Deployment / 部署状态

<!-- Choose one clearly / 明确选择当前状态 -->
- [ ] PR/code change only; **NOT deployed**. / 仅修改代码，未部署。
- [ ] Already deployed under separate authorization (include verified date/commit; never assume from merge alone). / 已获单独授权部署并核验（注明依据）。

## Review notes / 审核备注

<!-- Known limitations, follow-up work, screenshots without private data, compatibility caveats, release impacts / 已知限制、后续事项、安全截图、兼容性与发布影响。 -->
