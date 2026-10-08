# Fresh installation acceptance / 全新安装验收

## Scope and source / 范围与来源

Date: 2026-10-08. Source: a fresh HTTPS clone of GitHub
`hhb-coding/homelab-portal`, branch `docs/v0.1-release-prep`, starting at
`1da68eece65a9eb515dea90d5d70241092806c15`.
Application baseline remains `f261de40280dfd9cbd57a1c9ef24bf83e4fbd347`.
This acceptance changes documentation only; it does not alter the application.

在独立临时目录从 GitHub 全新克隆，使用新建虚拟环境、合成设备与隔离数据库。
不访问正式目录、不使用生产配置，不启动 HTTP 服务、不占用 8088、不修改 systemd。
测试 Token 仅供临时验收，未写入发布文件或报告。

## Results / 结果

| Check / 检查 | Result / 结果 |
|---|---|
| GitHub clone of preparation branch / 克隆发布准备分支 | PASS |
| New Python 3.12.3 venv; dependency installation from `requirements.txt` / 全新依赖安装 | PASS |
| `python -m pip check` / 依赖一致性 | PASS |
| Server, Linux and Windows configuration example fields/JSON / 示例配置字段与格式 | PASS |
| `.env` loading, loopback host, test port, debug disabled, isolated SQLite initialization / 配置加载与隔离初始化 | PASS |
| Flask/static compatibility suite / Flask 与静态兼容性测试 | 8 tests PASS |
| Lite frontend / Lite 前端 | 21 assertions PASS |
| Full/Network frontend / Full 与 Network 前端 | 45 assertions PASS |
| Python and JavaScript syntax / 语法 | PASS |
| Extra Flask test-client checks / 额外 Flask 测试客户端检查 | 19 responses PASS |

Flask tests used the **new checkout's new venv** and blocked external HTTP.
Node.js was unavailable locally; frontend suites from the fresh clone were
evaluated using the previously installed separate QuickJS test runtime and a
minimal `fs`/`vm` harness. This does not add runtime dependencies to the project,
and is not a native local Node.js result. GitHub CI runs the suites with Node 22.

Flask 测试使用新克隆的新环境；本机无 Node，前端采用独立 QuickJS 辅助环境，
执行的脚本来自新克隆。未将辅助运行时加入项目依赖，不声称本机 Node 验收通过。

The extra test-client checks covered `/`, `/lite`, health and database readiness,
empty device list, missing-device 404, empty/populated dashboard, missing-Beszel
503/502 responses, unauthorized/invalid/valid Heartbeat, IP-change logging,
single-device retrieval, a **mocked** Beszel-linked dashboard including zero CPU,
and four static assets. No request was sent to a real Beszel Hub or physical client.

额外检查验证页面、健康状态、空列表、404、Dashboard、缺少 Beszel 时的 503/502、
心跳鉴权/校验/登记、地址变更、单设备查询、模拟 Beszel 关联与零值、四个静态资源。
只通过 Flask 测试客户端运行，不启动服务，也不调用真实 Beszel 或设备。

## Documentation fixes / 文档修正

1. Install explicitly from `docs/v0.1-release-prep`. The former default clone
   selected `main`, which lacks the newer dashboard stages; the former subsequent
   checkout of only the application baseline removed release docs and safer examples.
   / 显式克隆发布准备分支，避免落到旧 main 或回退后丢失新版文档和示例。
2. Keep the complete preparation checkout; record its commit, then select an
   approved immutable **complete** revision for a later release/deployment.
   / 保留完整版本，记录 Commit，正式发布另行选择完整且不可变的最终版本。
3. Run the optional probe with `python tools/beszel_probe.py --url ...`, rather
   than assuming the script is executable by itself. / 探测工具命令明确使用 Python。

Revalidation: the corrected clone command matches the successful fresh clone;
returning to the preparation branch retains the new docs/config examples. Venv
installation, configuration and all listed tests passed on that branch. Shell
snippets were checked with `bash -n`; Markdown links and stated fields were checked.

修正后的克隆命令与成功执行的命令一致；回到准备分支后新版文档/示例保留。
安装、配置及上述测试通过，shell 命令语法、链接和字段一致性均已复查。

## Main and release composition / main 与发布组成

At acceptance, `origin/main` is
`84088cd861398d44e81b2bcf17c77a4907ab1aae`, an ancestor of the preparation branch,
with no commits unique to main. The preparation branch already contains these
six commits after main, plus this installation-documentation correction:

| Commit | Included change / 内容 |
|---|---|
| `e2e6aa0` | Mini Card layout / 6-A 摘要卡布局 |
| `48702cc` | Selectable Device Details / 6-B 设备详情选择 |
| `5e995d6` | Lite view and CI smoke tests / 6-C |
| `b82b4a8` | Network tab / 6-D |
| `f261de4` | UI cleanup and compatibility / 6-E |
| `1da68ee` | Bilingual release preparation / 双语发布资料 |

The eventual v0.1.0 commit must retain this complete history/content and the
installation fixes, plus the approved MIT License and any separately approved release metadata.
Tagging the current `main` or only the earlier application commit would omit
required functionality or release materials. No merge, tag or Release was performed.

最终发布需包含完整功能、发布文档、本次安装修正以及已确认的 MIT 许可证与另行批准的发布元数据。
直接标记现有 main 或仅使用旧应用 Commit 都会遗漏内容。本次未合并、建 Tag 或 Release。

## Not verified / 尚未验证

- Fresh install on a separate physical host or another Python/OS combination.
  / 独立实体主机或其他 Python/系统组合。
- Live Beszel authentication/linking and physical Linux/Windows clients.
  / 真实 Beszel 认证/关联与实体客户端上报。
- A Windows Task Scheduler task or systemd installation/startup.
  / Windows 定时任务与 systemd 安装/启动。
- Real browser layout, iOS 9 Safari Lite/Network and latest Full UI changes.
  / 真实浏览器布局、iOS 9 的 Lite/Network 与新版 Full。

These remain pending; they are not converted to PASS by mocked HTTP or JavaScript tests.
未完成项目保持待验收，模拟测试不能替代。
