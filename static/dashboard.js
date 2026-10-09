/*
 * HomeLab Portal live dashboard / 动态首页
 * ES5 + XMLHttpRequest are used for old Safari / iOS 9 compatibility.
 * 为兼容旧 Safari/iOS 9，使用 ES5 与 XMLHttpRequest。
 */
var DASHBOARD_URL = "/api/dashboard";
var REFRESH_MS = 5000;
var HISTORY_URL = "/api/history?minutes=60";
var HISTORY_REFRESH_MS = 60000;

/*
 * Persistent Beszel history / Beszel 持久化历史
 *
 * Filled from /api/history and used by the chart renderer.
 * 从 /api/history 读取，用于页面刷新后立即显示过去 60 分钟曲线。
 */
var beszelHistory = {};



/*
 * In-memory metric history / 浏览器内存中的指标历史
 *
 * 120 points x 5 seconds = approximately 10 minutes.
 * 120 个点 × 5 秒 ≈ 最近 10 分钟。
 *
 * Step 5A keeps history only while the page is open.
 * A later Step 5D will load persistent history from Beszel so that
 * refreshing the page does not erase the chart history.
 *
 * 第 5A 步只保存“当前页面打开期间”的历史。
 * 后续第 5D 步会从 Beszel 读取持久化历史，
 * 这样刷新页面后曲线仍能看到过去的数据。
 */
var HISTORY_MAX_POINTS = 120;
var metricHistory = {};

/* Step 6B selected device / 设备选择 */
var selectedDeviceId = null;
var latestDashboardData = null;


function historyValue(value) {

    var numberValue;

    if (value === null || value === undefined || (typeof value === "string" && /^\s*$/.test(value))) {
        return null;
    }

    numberValue = Number(value);

    if (typeof value === "boolean" || typeof value === "object" || !isFinite(numberValue)) {
        return null;
    }

    return numberValue;
}


function trimHistoryArray(items) {

    while (items.length > HISTORY_MAX_POINTS) {
        items.shift();
    }
}


function appendHistory(devices) {

    var now = new Date().getTime();
    var i;
    var device;
    var key;
    var item;

    for (i = 0; i < devices.length; i = i + 1) {

        device = devices[i];

        key = device.device_id
            || device.hostname
            || device.display_name;

        if (!key) {
            continue;
        }

        if (!metricHistory[key]) {
            metricHistory[key] = {
                timestamps: [],
                cpu: [],
                memory: [],
                disk: [],
                load1: []
            };
        }

        item = metricHistory[key];

        item.timestamps.push(now);
        item.cpu.push(historyValue(device.cpu_percent));
        item.memory.push(historyValue(device.memory_percent));
        item.disk.push(historyValue(device.disk_percent));
        item.load1.push(historyValue(device.load_1));

        trimHistoryArray(item.timestamps);
        trimHistoryArray(item.cpu);
        trimHistoryArray(item.memory);
        trimHistoryArray(item.disk);
        trimHistoryArray(item.load1);
    }
}


function getDeviceHistory(deviceId) {

    return metricHistory[deviceId] || null;
}

function esc(v) {
  if (v === null || v === undefined) { return ""; }
  return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function num(v, digits) {
  var n;
  if (v === null || v === undefined || (typeof v === "string" && /^\s*$/.test(v))) { return "—"; }
  n = Number(v);
  return typeof v === "boolean" || typeof v === "object" || !isFinite(n) ? "—" : n.toFixed(digits);
}

function pct(v) {
  var n = Number(v);
  if (!isFinite(n) || n < 0) { return 0; }
  return n > 100 ? 100 : n;
}

function metric(label, value) {
  var display = percentText(value);
  /* Missing values have no percentage or filled bar / 缺失指标不显示百分号或填充条。 */
  return '<div class="metric">'
    + '<span class="mlabel">' + esc(label) + '</span>'
    + '<span class="mvalue">' + display + '</span>'
    + '<span class="bar">' + (display === "—" ? "" : '<span class="fill" style="width:' + pct(value) + '%"></span>') + '</span>'
    + '</div>';
}

/* G/T abbreviate GiB/TiB, never nominal GB / G/T 表示 GiB/TiB，并非标称 GB。 */
function capacity(v) {
  if (num(v, 1) === "—" || Number(v) < 0) { return "—"; }
  return Number(v) >= 1024 ? (Number(v) / 1024).toFixed(1) + "T" : Number(v).toFixed(1) + "G";
}

function capacityOf(d, key) {
  var display = d.metrics_available === true && d.capacity_unit === "GiB" ? capacity(d[key]) : "—";
  if ((key === "disk_total" || key === "memory_total") && Number(d[key]) <= 0) { return "—"; }
  if ((key === "disk_used" || key === "disk_available")
      && (capacity(d.disk_total) === "—" || Number(d.disk_total) <= 0 || Number(d[key]) > Number(d.disk_total))) { return "—"; }
  /* Estimated space always carries ≈, including zero / 估算可用空间始终标注 ≈，包括零。 */
  if (key === "disk_available") {
    if (display === "—" || d.disk_available_estimated !== true
        || percentText(d.disk_usage_percent) === "—" || Number(d.disk_usage_percent) <= 0
        || capacity(d.disk_used) === "—" || Number(d.disk_used) <= 0
        || Number(d.disk_used) > Number(d.disk_total)) { return "—"; }
    /* Match the backend's rounded-sample feasibility check / 与后端的舍入区间合理性检查一致。 */
    var highPercent = Math.min(100, Number(d.disk_usage_percent) + 0.005);
    var lower = Math.max(0, Number(d.disk_used) - 0.005) * ((100 - highPercent) / highPercent);
    if (!isFinite(lower) || lower > Number(d.disk_total) - Number(d.disk_used) + 0.01) { return "—"; }
    return "≈" + display;
  }
  return display;
}

function percentText(v) {
  return num(v, 1) === "—" || Number(v) < 0 || Number(v) > 100 ? "—" : num(v, 1) + "%";
}

/* Keep labels inside each segment; hide when measured space is too narrow.
 * 容量文字限制在各自区段内；实测空间不足时隐藏，完整数值保留在无障碍说明中。 */
function fitDiskLabels() {
  var labels = document.querySelectorAll ? document.querySelectorAll(".disk-label") : [];
  var i, label;
  for (i = 0; i < labels.length; i += 1) {
    label = labels[i];
    label.style.visibility = label.parentNode.clientWidth >= label.offsetWidth + 12 ? "visible" : "hidden";
  }
}

function diskMetric(d) {
  var hasSample = d.capacity_unit === "GiB";
  var value = hasSample ? d.disk_usage_percent : d.disk_percent;
  var display = d.metrics_available === true ? percentText(value) : "—";
  if (hasSample && capacityOf(d, "disk_used") === "—") { display = "—"; }
  var width = display === "—" ? 0 : Number(value);
  var used = capacityOf(d, "disk_used"), available = capacityOf(d, "disk_available");
  var description = "Used / 已用: " + used + "; Available / 可用: " + available;
  /* A missing percentage cannot assign capacities to bar segments / 缺失比例时不定位容量。 */
  if (display === "—") { used = "—"; available = "—"; }
  /* Prefixes are measured with the full label; approximation stays in the note.
   * 按完整前缀文字测量区段宽度；近似含义保留在下方说明中。 */
  var usedLabel = "USED: " + used;
  var freeLabel = "FREE: " + available.replace(/^≈/, "");
  return '<div class="metric disk-metric"><span class="mlabel">Disk</span>'
    + '<span class="mvalue">' + display + '</span>'
    + '<span class="bar disk-bar" role="img" aria-label="' + esc(description) + '" title="' + esc(description) + '">'
    + '<span class="disk-used" style="width:' + width + '%"><span class="disk-label">' + usedLabel + '</span></span>'
    + '<span class="disk-free" style="width:' + (100 - width) + '%"><span class="disk-label">' + freeLabel + '</span></span>'
    + '</span></div>';
}

/* Time only in device details; Network retains its full timestamp / 详情仅显示时间，Network 保留完整时间戳。 */
function seenTime(value) {
  var parts = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/);
  if (!parts) { return "—"; }
  var date = new Date(Date.UTC(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]),
    Number(parts[4]), Number(parts[5]), Number(parts[6])));
  function pad(v) { return v < 10 ? "0" + v : String(v); }
  return pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
}

function uptime(seconds) {
  var s, d, h, m;
  if (num(seconds, 0) === "—") { return "—"; }
  s = Math.floor(Number(seconds));
  if (isNaN(s) || s < 0) { return "—"; }
  d = Math.floor(s / 86400);
  h = Math.floor((s % 86400) / 3600);
  m = Math.floor((s % 3600) / 60);
  if (d > 0) { return d + "d " + h + "h"; }
  if (h > 0) { return h + "h " + m + "m"; }
  return m + "m";
}

function temp(v) {
  var n = Number(v);
  if (num(v, 1) === "—" || n <= 0) { return "—"; }
  return n.toFixed(1) + " °C";
}

function localTime(value) {
  var parts, date;

  if (!value) { return "—"; }

  /*
   * SQLite CURRENT_TIMESTAMP is UTC.
   * SQLite CURRENT_TIMESTAMP 使用 UTC 时间。
   *
   * Parse manually instead of relying on Date.parse(), because
   * old Safari may not reliably parse "YYYY-MM-DD HH:MM:SS".
   * 手工解析，避免旧 Safari 对日期字符串格式兼容不一致。
   */
  parts = String(value).match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/
  );

  if (!parts) { return esc(value); }

  date = new Date(Date.UTC(
    Number(parts[1]),
    Number(parts[2]) - 1,
    Number(parts[3]),
    Number(parts[4]),
    Number(parts[5]),
    Number(parts[6])
  ));

  return date.toLocaleString();
}

function nameOf(d) {
  return d.display_name || d.hostname || d.device_id || "Unknown device";
}


function seriesMax(values, fixedMax) {
  var max = 0;
  var i;
  var v;

  if (fixedMax !== null && fixedMax !== undefined) {
    return fixedMax;
  }

  for (i = 0; i < values.length; i = i + 1) {
    v = values[i];

    if (v !== null && v !== undefined && !isNaN(Number(v))) {
      if (Number(v) > max) {
        max = Number(v);
      }
    }
  }

  if (max < 1) {
    max = 1;
  }

  return max * 1.15;
}


function sparkline(values, fixedMax) {
  var WIDTH = 300;
  var HEIGHT = 60;
  var maxValue = seriesMax(values, fixedMax);
  var points = "";
  var i;
  var x;
  var y;
  var v;
  var count = values.length;

  if (count < 2) {
    return '<div class="chart-wait">Collecting history...</div>';
  }

  for (i = 0; i < count; i = i + 1) {
    v = values[i];

    if (v === null || v === undefined || isNaN(Number(v))) {
      continue;
    }

    x = (i / (count - 1)) * WIDTH;
    y = HEIGHT - ((Number(v) / maxValue) * HEIGHT);

    if (y < 0) {
      y = 0;
    }

    if (y > HEIGHT) {
      y = HEIGHT;
    }

    if (points !== "") {
      points = points + " ";
    }

    points = points + x.toFixed(1) + "," + y.toFixed(1);
  }

  if (points === "") {
    return '<div class="chart-wait">No data</div>';
  }

  return '<svg class="sparkline" viewBox="0 0 300 60" preserveAspectRatio="none">'
    + '<line x1="0" y1="59.5" x2="300" y2="59.5" class="chart-baseline"></line>'
    + '<polyline points="' + points + '" class="chart-line"></polyline>'
    + '</svg>';
}


function latestHistoryValue(values) {
  var i;

  for (i = values.length - 1; i >= 0; i = i - 1) {
    if (values[i] !== null && values[i] !== undefined) {
      return values[i];
    }
  }

  return null;
}


function chartBox(label, values, fixedMax, unit) {
  var latest = latestHistoryValue(values);

  return '<div class="chart-box">'
    + '<div class="chart-title">' + esc(label)
    + '<span>' + num(latest, 1) + (num(latest, 1) === "—" ? "" : esc(unit || "")) + '</span></div>'
    + sparkline(values, fixedMax)
    + '<div class="chart-axis"><span>older</span><span>now</span></div>'
    + '</div>';
}


function seriesRange(values, minSpan, hardMin, hardMax) {
  var min = null;
  var max = null;
  var i;
  var n;
  var span;
  var center;
  var pad;

  for (i = 0; i < values.length; i = i + 1) {
    if (values[i] === null || values[i] === undefined || isNaN(Number(values[i]))) {
      continue;
    }

    n = Number(values[i]);

    if (min === null || n < min) { min = n; }
    if (max === null || n > max) { max = n; }
  }

  if (min === null || max === null) {
    min = (hardMin !== null && hardMin !== undefined) ? hardMin : 0;
    max = min + (minSpan || 1);
  }

  span = max - min;

  if (span < (minSpan || 1)) {
    center = (max + min) / 2;
    min = center - ((minSpan || 1) / 2);
    max = center + ((minSpan || 1) / 2);
  }

  pad = (max - min) * 0.08;
  min = min - pad;
  max = max + pad;

  if (hardMin !== null && hardMin !== undefined && min < hardMin) {
    min = hardMin;
  }

  if (hardMax !== null && hardMax !== undefined && max > hardMax) {
    max = hardMax;
  }

  if (max <= min) {
    max = min + 1;
  }

  return { min: min, max: max };
}


function sparklineZoom(values, minSpan, hardMin, hardMax) {
  var WIDTH = 300;
  var HEIGHT = 60;
  var range = seriesRange(values, minSpan, hardMin, hardMax);
  var span = range.max - range.min;
  var points = "";
  var i;
  var x;
  var y;
  var v;
  var count = values.length;

  if (count < 2) {
    return '<div class="chart-wait">Collecting live samples...</div>';
  }

  for (i = 0; i < count; i = i + 1) {
    v = values[i];

    if (v === null || v === undefined || isNaN(Number(v))) {
      continue;
    }

    x = (i / (count - 1)) * WIDTH;
    y = HEIGHT - (((Number(v) - range.min) / span) * HEIGHT);

    if (y < 0) { y = 0; }
    if (y > HEIGHT) { y = HEIGHT; }

    if (points !== "") {
      points = points + " ";
    }

    points = points + x.toFixed(1) + "," + y.toFixed(1);
  }

  if (points === "") {
    return '<div class="chart-wait">No data</div>';
  }

  return '<svg class="sparkline" viewBox="0 0 300 60" preserveAspectRatio="none">'
    + '<line x1="0" y1="59.5" x2="300" y2="59.5" class="chart-baseline"></line>'
    + '<polyline points="' + points + '" class="chart-line"></polyline>'
    + '</svg>';
}


function liveChartBox(label, values, minSpan, unit, hardMin, hardMax) {
  var latest = latestHistoryValue(values);

  return '<div class="chart-box">'
    + '<div class="chart-title">' + esc(label)
    + '<span>' + num(latest, 1) + (num(latest, 1) === "—" ? "" : esc(unit || "")) + '</span></div>'
    + sparklineZoom(values, minSpan, hardMin, hardMax)
    + '<div class="chart-axis"><span>older</span><span>now</span></div>'
    + '</div>';
}


function chartSection(d) {
  var key = d.device_id
    || d.hostname
    || d.display_name;

  var live = getDeviceHistory(key);
  var persistent = beszelHistory[key];
  var liveSamples = 0;
  var historySamples = 0;
  var h = "";

  /*
   * Two complementary timelines are shown:
   * - Live: browser-memory samples every 5 seconds, up to 10 minutes.
   * - History: Beszel persistent one-minute samples, up to 60 minutes.
   *
   * 同时显示两种时间尺度：
   * - Live：浏览器内每 5 秒采样，最多保留约 10 分钟。
   * - History：Beszel 持久化 1 分钟采样，显示约 60 分钟。
   */

  if (live && live.timestamps && live.timestamps.length > 0) {
    liveSamples = live.timestamps.length;

    h += '<div class="chart-section live-chart-section">'
      + '<div class="chart-header">Live trends <span>'
      + liveSamples
      + ' / '
      + HISTORY_MAX_POINTS
      + ' samples</span></div>'
      + '<div class="chart-grid">'
      + liveChartBox("CPU", live.cpu, 20, "%", 0, 100)
      + liveChartBox("RAM", live.memory, 10, "%", 0, 100)
      + liveChartBox("Load 1m", live.load1, 1, "", 0, null)
      + '</div>'
      + '<div class="chart-footnote">'
      + '5-second live samples / 10-minute rolling window / auto-scaled'
      + '</div>'
      + '</div>';
  }

  if (
    persistent
    && persistent.timestamps
    && persistent.timestamps.length > 1
  ) {
    historySamples = persistent.timestamps.length;

    h += '<div class="chart-section history-chart-section">'
      + '<div class="chart-header">Historical trends <span>'
      + historySamples
      + ' samples</span></div>'
      + '<div class="chart-grid">'
      + chartBox("CPU", persistent.cpu, 100, "%")
      + chartBox("RAM", persistent.memory, 100, "%")
      + chartBox("Load 1m", persistent.load1, null, "")
      + '</div>'
      + '<div class="chart-footnote">'
      + 'Beszel 1-minute history / 60-minute window'
      + '</div>'
      + '</div>';
  }

  return h;
}



function deviceKey(d) {
  return d.device_id || d.hostname || d.display_name || "";
}

function miniCard(d) {
  var state = networkState(d);
  var metrics = d.metrics_available === true;
  var key = deviceKey(d);
  var selectedClass = key === selectedDeviceId ? " selected-mini-card" : "";
  var h = '<div class="mini-card' + selectedClass + '" data-device="' + esc(key)
    + '" onclick="selectDeviceCard(this)">';

  h += '<div class="mini-card-head"><strong>' + esc(nameOf(d)) + '</strong>'
    + '<span class="' + (state === "online" ? "ok" : state === "offline" ? "bad" : "network-unknown") + '">'
    + state.toUpperCase() + '</span></div>';

  h += '<div class="mini-card-body">'
    + '<div><span>LAN</span><b>' + esc(d.lan_ip || "—") + '</b></div>';

  h += '<div><span>CPU</span><b>' + (metrics ? percentText(d.cpu_percent) : "—") + '</b></div>'
    + '<div><span>RAM (' + capacityOf(d, "memory_total") + ')</span><b>'
    + (metrics ? percentText(d.memory_percent) : "—") + '</b></div>'
    + '<div><span>DISK (' + capacityOf(d, "disk_total") + ')</span><b>'
    + (capacityOf(d, "disk_available") === "—" ? "—" : num(d.disk_available, 1) + "G") + '</b></div>';
  return h + '</div></div>';
}

function selectedDevice(list) {
  var i;
  if (!list || list.length === 0) { selectedDeviceId = null; return null; }
  if (selectedDeviceId) {
    for (i=0; i<list.length; i=i+1) {
      if (deviceKey(list[i]) === selectedDeviceId) { return list[i]; }
    }
  }
  selectedDeviceId = deviceKey(list[0]);
  return list[0];
}

function renderDevicePanels(list) {
  var mini="", detail="", chosen=selectedDevice(list), i;
  if (!list || list.length === 0) {
    mini = '<div class="loading">No devices registered.</div>';
    detail = mini;
  } else {
    for (i=0; i<list.length; i=i+1) { mini += miniCard(list[i]); }
    if (chosen) { detail = card(chosen); }
  }
  document.getElementById("mini-devices").innerHTML = mini;
  document.getElementById("devices").innerHTML = detail;
  fitDiskLabels();
}

function selectDeviceCard(element) {
  var key;
  if (!element) { return; }
  key = element.getAttribute("data-device");
  if (!key) { return; }
  selectedDeviceId = key;
  if (latestDashboardData) {
    renderDevicePanels(latestDashboardData.devices || []);
  }
}

function card(d) {
  var state = networkState(d);
  var h = '<div class="card">';
  h += '<div class="title"><h2>' + esc(nameOf(d)) + '</h2>'
    + '<b class="' + (state === "online" ? "ok" : state === "offline" ? "bad" : "network-unknown") + '">'
    + state.toUpperCase() + '</b></div>';

  /* Three rows share four aligned columns / 三行共用四列，标签与值对齐。 */
  h += '<table class="device-info"><colgroup><col class="info-label"><col class="info-value">'
    + '<col class="info-label"><col class="info-value"></colgroup><tbody>'
    + '<tr><th scope="row">LAN IP</th><td>' + esc(d.lan_ip || "—")
    + '</td><th scope="row">ZeroTier</th><td>' + esc(d.zerotier_ip || "—") + '</td></tr>'
    + '<tr><th scope="row">Last Seen</th><td>' + seenTime(d.last_seen)
    + '</td><th scope="row">Uptime</th><td>' + esc(uptime(d.uptime_seconds)) + '</td></tr>'
    + '<tr><th scope="row">Temperature</th><td>' + temp(d.temperature)
    + '</td><th scope="row">Load 1m / 5m</th><td>' + num(d.load_1,2) + ' / ' + num(d.load_5,2)
    + '</td></tr></tbody></table>';

  if (d.metrics_available === true) {
    h += '<div class="metrics">' + metric("CPU",d.cpu_percent)
      + metric("RAM",d.memory_percent) + diskMetric(d) + '</div>'
      + '<p class="capacity-note">G = GiB; T = TiB. System filesystem / 系统文件系统。'
      + ' FREE is estimated from Beszel; not exact statvfs availability / FREE 为 Beszel 估算可用空间，非 statvfs 精确值。'
      + (capacityOf(d, "disk_available") === "—" ? ' Estimate unavailable / 无可靠估算。' : '') + '</p>';
  } else {
    h += '<div class="unavailable">Beszel metrics unavailable</div>';
  }

  h += chartSection(d);

  return h + '</div>';
}

/* Switching panels never fetches data or resets selection / 切换不请求数据、不重置设备选择。 */
function selectDashboardTab(tab) {
  var network = tab === "network";
  document.getElementById("device-panel").className = network ? "hidden" : "";
  document.getElementById("network-panel").className = network ? "" : "hidden";
  document.getElementById("tab-device").className = "dashboard-tab" + (network ? "" : " active-tab");
  document.getElementById("tab-network").className = "dashboard-tab" + (network ? " active-tab" : "");
  document.getElementById("tab-device").setAttribute("aria-pressed", network ? "false" : "true");
  document.getElementById("tab-network").setAttribute("aria-pressed", network ? "true" : "false");
  if (!network) { fitDiskLabels(); }
}

/* Missing status is unknown, not a failed LAN check / 缺失状态为未知，并非 LAN 检测失败。 */
function networkState(device) {
  if (device.beszel_status === "up") { return "online"; }
  if (device.beszel_status === "down" || device.beszel_status === "paused") { return "offline"; }
  return "unknown";
}

function networkSummaryCard(label, value) {
  return '<div class="network-summary-card"><span>' + label + '</span><strong>' + value + '</strong></div>';
}

function renderNetworkPanels(list, sources) {
  var online = 0, offline = 0, unknown = 0, lan = 0, zerotier = 0;
  var cards = "", summary = "", i, device, state;
  var labels = { online: "ONLINE / 在线", offline: "OFFLINE / 离线", unknown: "UNKNOWN / 未知" };
  for (i = 0; i < list.length; i += 1) {
    device = list[i];
    state = networkState(device);
    if (state === "online") { online += 1; }
    else if (state === "offline") { offline += 1; }
    else { unknown += 1; }
    if (device.lan_ip) { lan += 1; }
    if (device.zerotier_ip) { zerotier += 1; }
    cards += '<div class="network-device-card"><h2>' + esc(nameOf(device)) + '</h2>'
      + '<p class="network-state ' + (state === "online" ? "ok" : state === "offline" ? "bad" : "network-unknown")
      + '">' + labels[state] + '</p><table><tr><td>LAN IP</td><td>' + esc(device.lan_ip || "—")
      + '</td></tr><tr><td>ZeroTier IP</td><td>' + esc(device.zerotier_ip || "—")
      + '</td></tr><tr><td>Last Seen / 最后心跳</td><td>' + localTime(device.last_seen) + '</td></tr></table>';
    if (!device.lan_ip) { cards += '<p class="network-note">LAN address unavailable / LAN 地址缺失</p>'; }
    if (!device.zerotier_ip) { cards += '<p class="network-note">No ZeroTier address reported (optional) / 未上报 ZeroTier 地址（可选）</p>'; }
    cards += '</div>';
  }
  summary += '<div class="network-summary-grid">'
    + networkSummaryCard("Devices / 设备总数", list.length)
    + networkSummaryCard("Online / 在线", online)
    + networkSummaryCard("Offline / 离线", offline)
    + networkSummaryCard("Unknown / 未知", unknown)
    + networkSummaryCard("LAN IP reported / 已上报", lan + " / " + list.length)
    + networkSummaryCard("ZeroTier IP reported / 已上报", zerotier + " / " + list.length)
    + '</div>';
  if (!sources || sources.metrics_status !== "ok") {
    summary += '<p class="network-note">Beszel status unavailable; addresses remain visible / Beszel 状态不可用，仍显示登记地址。</p>';
  }
  document.getElementById("network-summary").innerHTML = summary;
  document.getElementById("network-devices").innerHTML = cards || '<div class="loading">No devices registered / 暂无设备。</div>';
}

function render(data) {
  /* Reject broken payloads before replacing retained data / 替换旧数据前验证响应。 */
  if (!data || data.status !== "ok" || !Array.isArray(data.devices)) {
    throw new Error("Invalid dashboard response");
  }
  var list = [];
  var i;
  /* Ignore malformed entries; valid devices still render / 跳过无效条目，正常设备仍可显示。 */
  for (i = 0; i < data.devices.length; i += 1) {
    if (data.devices[i] && typeof data.devices[i] === "object" && !Array.isArray(data.devices[i])) {
      list.push(data.devices[i]);
    }
  }
  appendHistory(list);
  latestDashboardData = { devices: list, sources: data.sources };
  document.getElementById("device-count").innerHTML = list.length;

  if (data.sources && data.sources.metrics_status === "ok") {
    document.getElementById("metrics-status").innerHTML = '<span class="ok">ONLINE</span>';
  } else {
    document.getElementById("metrics-status").innerHTML = '<span class="bad">UNAVAILABLE</span>';
  }

  renderDevicePanels(list);
  renderNetworkPanels(list, data.sources);
  document.getElementById("dashboard-error").className = "error hidden";
  document.getElementById("last-updated").innerHTML =
    "Updated: " + new Date().toLocaleTimeString();
}

function fail() {
  document.getElementById("dashboard-error").className = "error";
  document.getElementById("dashboard-error").innerHTML =
    "Refresh failed. Displayed data may be stale; retrying automatically. / 刷新失败，显示数据可能过期，将自动重试。";
}

function installHistory(data) {
  var devices = data.devices || [];
  var i;
  var j;
  var device;
  var point;
  var item;

  for (i = 0; i < devices.length; i = i + 1) {
    device = devices[i];

    if (!device.device_id || !device.points) {
      continue;
    }

    item = {
      timestamps: [],
      cpu: [],
      memory: [],
      disk: [],
      load1: []
    };

    for (j = 0; j < device.points.length; j = j + 1) {
      point = device.points[j];

      item.timestamps.push(point.timestamp);
      item.cpu.push(historyValue(point.cpu_percent));
      item.memory.push(historyValue(point.memory_percent));
      item.disk.push(historyValue(point.disk_percent));
      item.load1.push(historyValue(point.load_1));
    }

    beszelHistory[device.device_id] = item;
  }
}


function loadHistory() {
  var x = new XMLHttpRequest();

  x.onreadystatechange = function () {
    var data;

    if (x.readyState !== 4) {
      return;
    }

    if (x.status >= 200 && x.status < 300) {
      try {
        data = JSON.parse(x.responseText);

        if (data.status === "ok") {
          installHistory(data);

          /*
           * Re-render immediately so the user sees the persistent
           * curves without waiting for the next 5-second refresh.
           *
           * 历史数据到达后立即重绘，不必等待下一次 5 秒刷新。
           */
          loadDashboard();
        }
      } catch (e) {
        /*
         * History is optional. The live fallback stays active.
         * 历史接口异常时继续使用实时缓存，不影响主 Dashboard。
         */
      }
    }
  };

  x.open(
    "GET",
    HISTORY_URL + "&_=" + new Date().getTime(),
    true
  );

  x.send(null);
}


function loadDashboard() {
  var x = new XMLHttpRequest();
  x.onreadystatechange = function () {
    var data;
    if (x.readyState !== 4) { return; }
    if (x.status >= 200 && x.status < 300) {
      try { data = JSON.parse(x.responseText); render(data); }
      catch (e) { fail(); }
    } else { fail(); }
  };
  x.open("GET", DASHBOARD_URL + "?_=" + new Date().getTime(), true);
  x.onerror = x.ontimeout = fail;
  x.timeout = 15000;
  x.send(null);
}

document.getElementById("tab-device").onclick = function () { selectDashboardTab("device"); };
document.getElementById("tab-network").onclick = function () { selectDashboardTab("network"); };

loadHistory();
loadDashboard();
setInterval(loadDashboard, REFRESH_MS);
setInterval(loadHistory, HISTORY_REFRESH_MS);

/* Re-measure after rotation or tab changes / 旋转或标签切换后重新测量。 */
if (typeof window !== "undefined") { window.addEventListener("resize", fitDiskLabels, false); }
