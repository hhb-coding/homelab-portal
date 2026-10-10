/* ES5 + XMLHttpRequest for iOS 9 Safari / 使用 ES5 和 XHR 兼容 iOS 9 Safari。 */
(function () {
  "use strict";
  var pending = false;
  var hasData = false;

  /* Escape API text before inserting HTML / 插入 HTML 前转义 API 文本。 */
  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function number(value, digits, suffix) {
    if (typeof value !== "number" || !isFinite(value)) { return "—"; }
    return value.toFixed(digits) + suffix;
  }

  /* Only trusted scheme-A samples yield an available percentage.
   * 仅可信方案 A 样本显示可用比例，分母为已用+估算可用，等价于 100-dp。 */
  function diskText(device, available) {
    var total = device.disk_total, used = device.disk_used, free = device.disk_available;
    var percent = device.disk_usage_percent;
    var validTotal = available && device.capacity_unit === "GiB"
      && typeof total === "number" && isFinite(total) && total > 0;
    var capacity = validTotal ? number(total >= 1024 ? total / 1024 : total, 1, total >= 1024 ? "T" : "G") : "—";
    var trusted = validTotal && device.disk_available_estimated === true
      && typeof used === "number" && isFinite(used) && used > 0 && used <= total
      && typeof free === "number" && isFinite(free) && free >= 0 && free <= total
      && typeof percent === "number" && isFinite(percent) && percent > 0 && percent <= 100;
    if (trusted) {
      var highPercent = Math.min(100, percent + 0.005);
      var lower = Math.max(0, used - 0.005) * ((100 - highPercent) / highPercent);
      trusted = isFinite(lower) && lower <= total - used + 0.01;
    }
    return 'Disk (' + capacity + ') 可用' + (trusted ? "≈" + number(100 - percent, 1, "%") : "—");
  }

  function card(device) {
    var status = device.beszel_status;
    var online = status === "up";
    var offline = status === "down" || status === "paused";
    var label = online ? "ONLINE / 在线" : offline ? "OFFLINE / 离线" : "UNKNOWN / 未知";
    var available = online && device.metrics_available === true;
    var name = device.display_name || device.hostname || device.device_id || "Unnamed device / 未命名设备";
    var html = '<article class="lite-card"><h2><span class="status '
      + (online ? "online" : offline ? "offline" : "unknown") + '">' + label
      + '</span>' + (offline ? OfflineSeen.html(device.last_seen) : '') + esc(name) + '</h2><p class="addresses">LAN IP: '
      + esc(device.lan_ip || "—");
    if (device.zerotier_ip) { html += '<br>ZeroTier IP: ' + esc(device.zerotier_ip); }
    html += '</p><div class="metrics">';
    html += '<span class="metric">CPU: ' + number(available ? device.cpu_percent : null, 1, "%") + '</span>';
    html += '<span class="metric">RAM: ' + number(available ? device.memory_percent : null, 1, "%") + '</span>';
    html += '<span class="metric">' + diskText(device, available) + '</span>';
    html += '<span class="metric">Load 1m / 负载: ' + number(available ? device.load_1 : null, 2, "") + '</span></div>';
    /* Offline values can be stale / 离线设备的指标可能过期，因此不显示。 */
    if (!available) { html += '<p class="note">Current metrics unavailable / 当前指标不可用</p>'; }
    return html + '</article>';
  }

  function render(data) {
    var html = "", i, count = 0;
    if (!data || data.status !== "ok" || !Array.isArray(data.devices)) {
      throw new Error("Invalid dashboard response");
    }
    OfflineSeen.sync(data.server_time);
    for (i = 0; i < data.devices.length; i += 1) {
      /* One invalid record must not hide other devices / 单条无效数据不影响其他设备。 */
      if (!data.devices[i] || typeof data.devices[i] !== "object" || Array.isArray(data.devices[i])) { continue; }
      html += card(data.devices[i]);
      count += 1;
    }
    document.getElementById("lite-devices").innerHTML = html || '<p>No devices registered / 暂无设备。</p>';
    document.getElementById("lite-summary").innerHTML = 'Devices / 设备: ' + count
      + ' · Updated / 更新: ' + esc(new Date().toLocaleTimeString())
      + (data.sources && data.sources.metrics_status !== "ok" ? ' · Metrics unavailable / 指标不可用' : '');
    document.getElementById("lite-error").className = "hidden";
    hasData = true;
  }

  function fail() {
    var error = document.getElementById("lite-error");
    error.innerHTML = 'Unable to refresh. Retrying automatically / 刷新失败，将自动重试。'
      + (hasData ? ' Displayed data is stale / 显示的数据已过期。' : '');
    error.className = "";
    if (!hasData) { document.getElementById("lite-summary").innerHTML = 'Data unavailable / 数据不可用'; }
  }

  function refresh() {
    var xhr;
    if (pending) { return; }
    pending = true;
    xhr = new XMLHttpRequest();
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      pending = false;
      if (xhr.status >= 200 && xhr.status < 300) {
        try { render(JSON.parse(xhr.responseText)); } catch (error) { fail(); }
      } else { fail(); }
    };
    xhr.onerror = xhr.ontimeout = function () { pending = false; fail(); };
    try {
      xhr.open("GET", "/api/dashboard?_=" + new Date().getTime(), true);
      xhr.timeout = 15000;
      xhr.send(null);
    } catch (error) { pending = false; fail(); }
  }

  refresh();
  setInterval(refresh, 5000);
}());
