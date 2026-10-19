# Contributing to HomeLab Portal / 参与 HomeLab Portal 开发

Thank you for helping improve HomeLab Portal. This is a **public, self-hosted** project. Its maintainers may use AI coding assistants; the same review, testing and security rules apply to human- and AI-authored changes.

感谢参与 HomeLab Portal。这是**公开的自托管**项目。人工与 AI/Codex 生成的修改必须遵循同样的审查、安全和测试流程。

## Source of truth / 需求依据

- **Published versions** are immutable Git tags and GitHub Releases (e.g. `v0.2.0`). An internal `Step 7.03` is a work-package number, **not** a published `v7.03` release.
- Current development plan: [docs/ROADMAP.md](docs/ROADMAP.md). Use the specific GitHub Issue or approved design document for a step's detailed acceptance criteria, e.g. [Step 7.03 / Issue #11](https://github.com/hhb-coding/homelab-portal/issues/11).
- Record separately: **approved requirement → implementation branch → reviewed/merged PR → deployed to a host → operationally verified**. No stage implies the next.

- **正式发布版本**以 GitHub Tag/Release 为准；`Step 7.03` 是开发任务编号，不代表 `v7.03` 已发布。
- 统一规划看 [ROADMAP](docs/ROADMAP.md)，详细需求以对应 Issue/已批准方案为准。需求批准、代码合并、生产部署、实际运行验证必须分别记录。

## Safe working procedure / 安全开发流程

1. Check the current GitHub `main`, open PRs and related Issues before opening a branch. On a host, **inspect development and production worktrees independently**: `git status --short --branch`, current commit, uncommitted changes, active services and timers. Never assume they match GitHub.
2. Make an isolated `feat/...`, `fix/...` or `docs/...` branch. Do not develop directly in a live production checkout, reset someone else's branch or force-push a shared branch.
3. Keep commits focused; update relevant bilingual README/docs and test cases. Preserve existing legacy-browser ES5/XHR compatibility unless a documented requirement explicitly supersedes it.
4. Open a PR into `main`. Fill out the PR template. Wait for CI and examine the actual diff, not just the green checkmark. Review approval and merging are separate actions.
5. **Never automatically deploy, restart a service, activate a timer, migrate production SQLite, or overwrite a private configuration file.** Production changes require separate owner approval, a backup/recovery path and post-deployment verification.

1. 开发前分别确认 GitHub `main`、相关 Issue/PR、HP 开发目录和生产目录的分支、提交、未提交修改及正在运行的服务。
2. 使用独立 `feat/`、`fix/`、`docs/` 分支，不直接修改生产工作树；不强制覆盖他人修改。
3. 补齐中英文说明与必要测试；保留旧 Safari 的 ES5/XHR 兼容性。
4. 创建 PR、核对真实变更、等待 CI，再由维护者审核合并。
5. **合并代码不等于授权部署**；重启、安装 timer、生产数据库迁移等必须单独批准，准备备份与回滚措施。

## Testing / 测试

The CI workflow is [`.github/workflows/ci.yml`](.github/workflows/ci.yml), named **Smoke tests**. The default job is **test**. It runs on pushes and pull requests with Python 3.12 and Node 22, without production secrets.

Run these in a clean, isolated development environment:

```sh
python -B -m unittest discover -s tests -v
python -B -c "import ast, pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path('.').rglob('*.py') if '.venv' not in p.parts]"
node --check static/dashboard.js
node --check static/lite.js
node --check static/offline-seen.js
node tests/test_lite.js
node tests/test_network.js
node tests/test_device_v3.js
node tests/test_freshness.js
node tests/test_offline_seen.js
```

Some layout/browser and real-device tests are separate from CI; do **not** report those as passed simply because CI is green. For documentation-only changes, CI still runs, and reviewers must check links, claims, release status and diff scope.

CI 在 `push` 和 `pull_request` 事件执行。自动测试通过**不等于**实机浏览器验收或生产运行验证；文档修改也需要审阅链接、版本事实和实际 diff。

## Public repository safety / 公开仓库安全

- Never commit real LAN/WAN IPs, device IDs tied to a private environment, private domains, Caddy/Cloudflare endpoint names, usernames, tokens, passwords, hashes, authentication headers, production log contents, backup archives or SQLite databases.
- Use placeholders and tracked `*.example` files. Keep real `.env` and local client settings outside Git. `.gitignore` is **not** a secret scanner.
- If a real credential accidentally enters Git history, **stop**, notify the owner privately and rotate/revoke the credential. Do not rely on deleting the current file or silently rewriting Git history.
- Caddy/Cloudflare and other public exposure settings require a separate security review; this repository's Flask read APIs do not include built-in Portal login.

严禁提交真实私网 IP、域名、账号、Token、密码、哈希、访问日志、SQLite 或生产备份。示例文件只用占位符；如发现密钥泄漏，先停止操作并私下处理凭据轮换，不能只删除当前文件就认为历史安全。

## Branches, reviews and releases / 分支、审查和版本

- Do not delete a remote branch just because its commits are ancestors of `main`: first confirm no development checkout, worktree, automation, release process or open PR still uses it. Keep older branches until these checks can be made; do not rewrite published tags.
- As of 2026-10-19, the public repository's `main` was observed **without branch protection/rulesets**. These instructions are **policy guidance, not enforced GitHub settings**. The owner may enable a `main` ruleset in **Settings → Rules → Rulesets**: require PRs and successful `test` CI status, prevent force pushes and deletion of `main`; review any bypass/reviewer restrictions against a single-maintainer workflow before enabling. The connector used to prepare this document cannot change these repository settings.
- Published GitHub Release descriptions and tags are historical records. Correct inaccuracies transparently, e.g. an erratum in [CHANGELOG.md](CHANGELOG.md), and seek separate maintainer authorization for any direct published-release edits or new tags.

删除 GitHub 旧分支前，应核实本地开发目录、工作树、自动化及未结束的 PR 是否仍引用它；已发布 Tag 不可随意改写。2026-10-19 检查发现 `main` 尚未启用保护规则；以上是**建议流程，不是自动强制策略**。建议有条件地设置 PR + `test` 检查，不要让单维护者被错误的审批规则锁住。
