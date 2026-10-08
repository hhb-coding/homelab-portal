# Browser validation / 浏览器验收

The Full page was previously confirmed to display correctly on real iOS 9
Safari. That historical result does not certify these new UI changes.
Lite and the new Network view have **not** been tested on real iOS 9 Safari.
The items below remain pending until someone performs and records the checks.

完整视图此前已确认在真实 iOS 9 Safari 正常显示，但不代表本次改动已完成实测。
Lite 和新版 Network **尚未**进行 iOS 9 实机测试。以下项目需实际验收后记录，
不能用自动化测试替代或直接标记通过。

- [ ] Desktop, tablet and phone at 320/375, 768/1024 and 1280 px: no horizontal
  page scrolling, overlapping buttons, clipped names or unreadable addresses.
  / 桌面、平板、手机对应宽度下无页面横向滚动、按钮重叠或文字截断。
- [ ] Real old iPad, iOS 9 Safari, portrait and landscape: repeat layout checks
  for Full Device, Network and Lite; record device, OS, date and result.
  / 旧 iPad 竖屏和横屏验证三种视图，记录设备、系统、日期和结果。
- [ ] Device Mini Card selection, details, live/persistent SVG charts and
  Device/Network switching retain the selected device through refreshes.
  / 设备选择、详情、实时和历史 SVG 图表及标签切换在刷新后保持正常。
- [ ] Lite Style and Full View links work; Lite loads no history or charts.
  / 双向导航正常，Lite 不加载历史或图表。
- [ ] Empty registry, offline/unknown devices, optional missing addresses,
  missing metrics and real zero values display distinct, understandable states.
  / 空列表、离线、未知、可选地址缺失、缺失指标和真实零值显示准确。
- [ ] In a development test environment, simulate API errors, timeout and
  recovery: retained data is marked stale and successful refresh clears errors.
  / 在开发测试环境模拟 API 失败、超时和恢复，旧数据提示与恢复正常。

Automated checks use temporary SQLite and mock requests; they verify behavior
and syntax, not real-device rendering. / 自动化测试使用临时数据库和模拟请求，
验证逻辑与语法，不代表真实设备视觉验收。

## Automated coverage / 自动化覆盖

Run the Flask smoke suite and `node tests/test_lite.js`, `node tests/test_network.js`
as described in the README. These exercise empty/partial data, status display,
errors/timeouts, navigation and tab selection using mocks, not real Safari.

按 README 运行 Flask 与 JavaScript 测试；覆盖空数据、缺失指标、状态、错误、
超时、导航和标签选择。模拟测试不能替代真实 Safari 验收。
