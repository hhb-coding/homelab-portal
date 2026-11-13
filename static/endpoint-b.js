/* Endpoint B HTTP discovery; ES5 + XHR / 保留旧 Safari 兼容。 */
var endpointBState = null, endpointBBusy = false, endpointBError = "", endpointBRequest = null;

function renderEndpointB() {
  var el = document.getElementById("endpoint-b-controls"), data = endpointBState, d = data && data.discovery,
    html = '', text = '', options = '', i, m, selected = data && data.selected_monitor_id, pending = null;
  if (!el) { return; }
  if (d) {
    if (d.status === "unique") { text = d.matches[0] + ' · 请在 Beszel 更新探测目标'; }
    else if (d.status === "multiple") { text = '找到多个 TL-WDR5620：' + d.matches.join('、') + '。请核对设备后重新查找。'; }
    else { text = '未找到 TL-WDR5620，请检查设备连通性和服务器扫描范围。'; }
  }
  html = '<div class="endpoint-b-discovery"><button type="button" id="endpoint-b-discover"' + (endpointBBusy ? ' disabled' : '') + '>'
    + (endpointBBusy ? '处理中…' : '查找 TP-Link') + '</button><span role="status" aria-live="polite">' + esc(text || '按需查找 TL-WDR5620 管理地址') + '</span></div>';
  if (d && d.status === "unique") {
    for (i = 0; i < data.monitors.length; i += 1) {
      m = data.monitors[i];
      if (m.target !== d.matches[0]) { continue; }
      options += '<option value="' + esc(m.id) + '"' + (m.id === selected ? ' selected' : '') + '>' + esc(m.target + ' · HP ICMP · ' + m.interval + 's') + '</option>';
    }
    if (!selected) { options = '<option value="" selected>' + esc(d.matches[0]) + ' · 等待 Beszel 更新</option>' + options; }
    html += '<label for="endpoint-b-monitor">HP ICMP 探测</label><select id="endpoint-b-monitor"' + (endpointBBusy ? ' disabled' : '') + '>' + options + '</select>';
    text = { waiting_beszel: '等待 Beszel 更新', ambiguous: '存在多个对应 HP ICMP 探测，请在 Beszel 核对后刷新',
      beszel_unavailable: 'Beszel 暂不可用，请稍后刷新', expired: '发现结果已过期，请重新查找',
      role_conflict: '此地址已用于其他 Network 角色，请核对配置', ready: '已检测到对应 HP ICMP 探测，可以保存映射' }[data.probe_status] || '';
    html += '<div class="endpoint-b-actions"><button type="button" id="endpoint-b-refresh"' + (endpointBBusy ? ' disabled' : '') + '>刷新探测</button>'
      + '<button type="button" id="endpoint-b-save"' + (!data.can_save || endpointBBusy ? ' disabled' : '') + '>保存映射</button></div>'
      + '<p class="endpoint-b-status" role="status" aria-live="polite">' + esc(text) + '</p>';
  }
  if (typeof networkHistoryData !== "undefined" && networkHistoryData) {
    for (i = 0; i < networkHistoryData.targets.length; i += 1) {
      m = networkHistoryData.targets[i];
      if (m.role === "endpoint_b") { pending = m.mapping_status; }
    }
  }
  if (pending) { html += '<p class="endpoint-b-mapping" role="status">' + (pending === "active" ? '映射已生效 · 卡片与曲线使用同一归档探测' : '映射已保存 · 等待首个归档样本') + '</p>'; }
  if (endpointBError) { html += '<p class="endpoint-b-status" role="alert">' + esc(endpointBError) + '</p>'; }
  el.innerHTML = html;
}

function endpointBCall(action) {
  var x, select, payload = {}, url = "/api/network/endpoint-b";
  if (endpointBBusy) { return; }
  if (action === "save") {
    select = document.getElementById("endpoint-b-monitor");
    if (!endpointBState || !endpointBState.can_save || !select || select.value !== endpointBState.selected_monitor_id) { return; }
    payload = { discovery_id: endpointBState.discovery.id, monitor_id: select.value };
  }
  if (action === "discover") { url += "/discover"; }
  endpointBBusy = true; endpointBError = ""; renderEndpointB();
  x = new XMLHttpRequest(); endpointBRequest = x;
  function finish() {
    var data = null, errors = { discovery_not_configured: '服务器尚未配置 TP-Link 扫描范围', invalid_discovery_config: '服务器扫描配置无效',
      discovery_busy: '服务器正在查找或保存，请稍后重试', discovery_cooldown: '查找过于频繁，请等待 30 秒后重试',
      discovery_failed: 'HTTP 查找失败，请检查服务器 curl 与网络', mapping_not_ready: '探测或发现结果已变化，请刷新后重试' };
    if (endpointBRequest !== x) { return; }
    endpointBRequest = null; endpointBBusy = false;
    try { data = JSON.parse(x.responseText); } catch (e) {}
    if (x.status >= 200 && x.status < 300 && data && data.status === "ok") {
      endpointBState = data;
      if (action === "save") { loadNetworkHistory(); }
    } else {
      endpointBError = errors[data && data.error] || '暂时无法完成操作，请稍后重试';
      if (endpointBState) { endpointBState.can_save = false; }
    }
    renderEndpointB();
  }
  x.onreadystatechange = function () { if (x.readyState === 4) { finish(); } };
  x.open(action === "refresh" ? "GET" : "POST", url, true);
  x.timeout = action === "discover" ? 60000 : 30000;
  x.onerror = x.ontimeout = finish;
  if (action !== "refresh") { x.setRequestHeader("Content-Type", "application/json"); x.setRequestHeader("X-Portal-Request", "1"); }
  x.send(action === "refresh" ? null : JSON.stringify(payload));
}

if (document.addEventListener) {
  document.addEventListener("click", function (event) {
    var id = event.target && event.target.id;
    if (id === "endpoint-b-discover") { endpointBCall("discover"); }
    if (id === "endpoint-b-refresh") { endpointBCall("refresh"); }
    if (id === "endpoint-b-save") { endpointBCall("save"); }
  }, false);
}
endpointBCall("refresh");
setInterval(function () { if (endpointBState && endpointBState.discovery && endpointBState.discovery.status === "unique") { endpointBCall("refresh"); } }, 15000);
