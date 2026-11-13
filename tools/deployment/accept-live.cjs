'use strict';
// Real Portal page and actual DOM clicks. No Fetch interception, fixture or mocked API.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {hasEvidence} = require('./sample-evidence.cjs');
const output = process.argv[2], probeOnly = process.argv[3] === '--probe';
const runtime = probeOnly ? null : JSON.parse(fs.readFileSync(path.join(output, 'runtime.private.json'), 'utf8'));
const executable = process.env.CHROMIUM_BINARY || '/home/daniel/.cache/ms-playwright/chromium-1187/chrome-linux/chrome';
const profile = path.join(output, probeOnly ? 'probe-profile' : 'live-profile');
fs.mkdirSync(profile, {recursive: true, mode: 0o700});
const browser = spawn(executable, ['--headless', '--no-sandbox', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--disable-gpu', '--disable-dev-shm-usage', '--remote-debugging-pipe',
  '--user-data-dir=' + profile], {stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe']});
let sequence = 0, buffer = '', session, stderr = '', exited = false, closing = false;
const pending = new Map(), errors = [];
function cdp(method, params = {}, sessionId = session) {
  return new Promise((resolve, reject) => {
    if (exited) return reject(Error('Chromium exited: ' + stderr));
    const id = ++sequence, timer = setTimeout(() => {pending.delete(id); reject(Error('CDP timeout: ' + method));}, 30000);
    pending.set(id, {resolve, reject, timer});
    browser.stdio[3].write(JSON.stringify({id, method, params, sessionId}) + '\0');
  });
}
function rejectAll(error) {
  for (const p of pending.values()) {clearTimeout(p.timer); p.reject(error);}
  pending.clear();
}
for (const pipe of [browser.stdio[3], browser.stdio[4]]) pipe.on('error', () => {});
browser.on('error', error => {exited = true; rejectAll(error);});
browser.on('exit', (code, signal) => {
  exited = true;
  if (!closing) rejectAll(Error('Chromium exited ' + (signal || code) + ': ' + stderr));
});
browser.stderr.on('data', data => {stderr = (stderr + data).slice(-6000);});
browser.stdio[4].on('data', data => {
  buffer += data;
  let at;
  while ((at = buffer.indexOf('\0')) >= 0) {
    const message = JSON.parse(buffer.slice(0, at)); buffer = buffer.slice(at + 1);
    if (message.id && pending.has(message.id)) {
      const p = pending.get(message.id); pending.delete(message.id); clearTimeout(p.timer);
      message.error ? p.reject(Error(JSON.stringify(message.error))) : p.resolve(message.result);
    } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
  }
});
async function evaluate(expression) {
  const r = await cdp('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  assert(!r.exceptionDetails, JSON.stringify(r.exceptionDetails));
  return r.result.value;
}
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(expression, seconds = 60) {
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    if (await evaluate(expression)) return;
    await delay(500);
  }
  throw Error('Timed out: ' + expression);
}
async function click(id) {
  assert(await evaluate('!!document.getElementById(' + JSON.stringify(id) + ')'), 'Missing control: ' + id);
  await evaluate('document.getElementById(' + JSON.stringify(id) + ').click()');
}
function write(name, data) {
  fs.writeFileSync(path.join(output, name), JSON.stringify(data, null, 2) + '\n', {mode: 0o600});
}
async function screenshot(name) {
  await evaluate('document.querySelector("[data-network-card=endpoint_b]").scrollIntoView()');
  const r = await cdp('Page.captureScreenshot', {format: 'png'});
  fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(r.data, 'base64'), {mode: 0o600});
}
async function run() {
  await cdp('Browser.getVersion', {}, undefined);
  if (probeOnly) {console.log('SSH Chromium/CDP 启动检查：通过'); return;}
  const target = await cdp('Target.createTarget', {url: 'about:blank'}, undefined);
  session = (await cdp('Target.attachToTarget', {targetId: target.targetId, flatten: true}, undefined)).sessionId;
  await cdp('Page.enable'); await cdp('Runtime.enable');
  await cdp('Emulation.setDeviceMetricsOverride', {width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false});
  await cdp('Page.navigate', {url: runtime.base_url + '/'});
  await until('typeof endpointBState!=="undefined" && endpointBState && document.getElementById("tab-network")');
  await click('tab-network');
  await until('document.getElementById("endpoint-b-discover") && typeof networkHistoryData!=="undefined" && networkHistoryData');
  // One actual click, bounded RFC1918 scan performed by the production server.
  await click('endpoint-b-discover');
  await until('!endpointBBusy', 90);
  let state = await evaluate('endpointBState');
  write('discovery.private.json', state);
  assert(state.discovery && state.discovery.status === 'unique' && state.discovery.matches.length === 1,
    '真实发现不是唯一 TL-WDR5620；详情见 discovery.private.json');
  assert.equal(state.discovery.system_id, runtime.system_id);
  const ip = state.discovery.matches[0], receipt = state.discovery.id;
  console.log('真实 TP-Link 唯一发现：' + ip + '；核对在线 Beszel 的 HP ICMP 探测。');
  const readyDeadline = Date.now() + 480000;
  if (!state.can_save) console.log('等待 Beszel 中唯一启用的 HP ICMP 目标更新为 ' + ip + '（最多 8 分钟，脚本每 15 秒刷新）。');
  while (!state.can_save && Date.now() < readyDeadline) {
    await delay(15000); await until('!endpointBBusy'); await click('endpoint-b-refresh');
    await until('!endpointBBusy'); state = await evaluate('endpointBState');
    assert(state.discovery && state.discovery.id === receipt, 'Discovery receipt changed');
    if (['expired', 'role_conflict', 'ambiguous'].includes(state.probe_status)) break;
  }
  write('probe-ready.private.json', state);
  assert.equal(state.probe_status, 'ready', 'Beszel 未提供唯一可保存的 HP ICMP；不会修改 Beszel');
  assert(state.can_save);
  const matches = state.monitors.filter(m => m.target === ip);
  assert.equal(matches.length, 1); assert.equal(matches[0].id, state.selected_monitor_id);
  assert.equal(await evaluate('document.getElementById("endpoint-b-monitor").value'), matches[0].id);
  assert.equal(await evaluate('document.getElementById("endpoint-b-save").disabled'), false);
  await screenshot('ready-desktop');
  await click('endpoint-b-save'); await until('!endpointBBusy');
  state = await evaluate('endpointBState');
  assert(state.mapping, 'Save mapping failed');
  assert.equal(state.mapping.target, ip); assert.equal(state.mapping.monitor_id, matches[0].id);
  const savedAt = state.mapping.saved_at * 1000;
  write('mapping-saved.private.json', state);
  console.log('映射已保存；等待既有归档 timer 自然执行并写入保存之后的新样本（最多 25 分钟）。');
  const archiveDeadline = Date.now() + 1500000;
  let endpoint;
  while (Date.now() < archiveDeadline) {
    await evaluate('loadNetworkHistory()');
    await until('networkHistoryRequest && networkHistoryRequest.readyState===4');
    endpoint = await evaluate('networkHistoryData.targets.filter(t=>t.role==="endpoint_b")[0]');
    write('latest-observation.private.json', {saved_at_ms: savedAt, endpoint});
    if (hasEvidence(endpoint, savedAt, ip)) break;
    await delay(15000);
  }
  assert(endpoint && endpoint.latest_sample && endpoint.latest_sample.time > savedAt
    && endpoint.latest_sample.count > 0, '未收到保存之后的新归档样本');
  assert(Date.now() - endpoint.latest_sample.time < 720000, 'Endpoint B 样本已过期');
  assert(endpoint.rows.some(p => p.time > savedAt && p.success_count > 0), '已收到新归档，但保存后的探测尚无成功响应');
  const report = [];
  for (const width of [1440, 390]) {
    await cdp('Emulation.setDeviceMetricsOverride', {width, height: 1100, deviceScaleFactor: 1, mobile: width < 600});
    await delay(700); await evaluate('renderNetworkPlots(); renderEndpointB()');
    endpoint = await evaluate('networkHistoryData.targets.filter(t=>t.role==="endpoint_b")[0]');
    assert(endpoint.target === ip && endpoint.mapping_status === 'active' && endpoint.latest_sample.time > savedAt
      && endpoint.rows.some(p => p.time === endpoint.latest_sample.time && p.count > 0));
    assert.equal(await evaluate('document.querySelector("[data-network-card=endpoint_b] .network-target-ip").textContent'), ip);
    assert(await evaluate('document.querySelector("[data-network-card=endpoint_b]").textContent.includes(' + JSON.stringify((endpoint.latest_sample.rtt_ms === null ? '—' : endpoint.latest_sample.rtt_ms.toFixed(2) + ' ms')) + ')'), '卡片 RTT 与真实新样本不同');
    assert(await evaluate('document.querySelector(".endpoint-b-mapping").textContent.includes("映射已生效")'));
    await evaluate('document.querySelector("#network-rtt-private-chart [data-network-legend=endpoint_b]").click()');
    assert.equal(await evaluate('document.querySelector("#network-rtt-private-chart-stats .network-target-ip").textContent'), ip);
    assert(await evaluate('networkHistoryData.targets.filter(t=>t.role==="endpoint_b")[0].rows.some(p=>p.time===' + endpoint.latest_sample.time + ')'));
    assert(await evaluate('document.querySelector("#network-rtt-private-chart [data-network-series=endpoint_b] title").textContent.includes(' + JSON.stringify(ip) + ')'));
    assert(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), '页面横向溢出');
    await screenshot('active-' + width);
    report.push({width, card_target: ip, curve_target: ip, new_sample: endpoint.latest_sample});
  }
  assert.deepEqual(errors, [], '生产页面发生 JavaScript 异常');
  write('live-browser.private.json', {accepted: true, reachability: endpoint.latest_sample.success_count > 0 ? 'responding' : 'all_probes_failed', target: ip, monitor_id: matches[0].id,
    post_save_success_samples: endpoint.rows.filter(p=>p.time>savedAt && p.success_count>0), archive_id: endpoint.monitor_id, saved_at_ms: savedAt, discovery: receipt, report, errors});
  console.log('真实页面桌面/手机卡片、曲线、同址统计与新样本：通过');
}
const watchdog = setTimeout(() => {rejectAll(Error('Live browser exceeded 36 minutes')); browser.kill();}, 2160000);
run().catch(async error => {
  process.exitCode = 1;
  write('browser-failure.private.json', {error: error.stack || error.message, errors, stderr});
  console.error('浏览器验收失败：' + error.message);
  if (session && !exited) {try {await screenshot('failure');} catch (_) {}}
}).finally(async () => {
  clearTimeout(watchdog); closing = true;
  if (!exited) {
    try {await cdp('Browser.close', {}, undefined);} catch (_) {}
    browser.kill();
  }
  for (const p of pending.values()) clearTimeout(p.timer);
  pending.clear();
});
