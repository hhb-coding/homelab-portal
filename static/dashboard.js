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
var networkRange = "1h", networkSelected = {}, networkHistoryRequest = null, networkHistoryData = null;
var networkCharts = {
  "network-rtt-private-chart": { key: "rtt_ms", pinned: "upstream_gateway", hover: null },
  "network-rtt-public-chart": { key: "rtt_ms", pinned: "public_primary", hover: null },
  "network-loss-chart": { key: "loss_pct", pinned: "upstream_gateway", hover: null }
};


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

/* Numeric GHz only; preserve missing data / 仅接受数值型 GHz，缺失时保留占位符。 */
function frequency(v) {
  return typeof v === "number" && isFinite(v) && v > 0 ? v.toFixed(2) + " GHz" : "—";
}

function temp(v) {
  var n = v;
  if (typeof n !== "number" || !isFinite(n) || n <= 0) { return "—"; }
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
    + (state === "offline" ? '<span class="offline-status-row">' : '')
    + '<span class="' + (state === "online" ? "ok" : state === "offline" ? "bad" : "network-unknown") + '">'
    + state.toUpperCase() + '</span>'
    + (state === "offline" ? '</span>' + OfflineSeen.html(d.last_seen) : '') + '</div>';

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

/* Keep the float layout on iOS 9; only reserve extra height when hints exist. */
function equalMiniCards() {
  var cards = document.querySelectorAll ? document.querySelectorAll(".mini-card") : [], i, height = 0;
  for (i = 0; i < cards.length; i += 1) { cards[i].style.height = ""; }
  if (!document.querySelectorAll || !document.querySelectorAll(".mini-card .offline-seen").length) { return; }
  for (i = 0; i < cards.length; i += 1) { height = Math.max(height, cards[i].getBoundingClientRect().height); }
  for (i = 0; i < cards.length; i += 1) { cards[i].style.height = Math.ceil(height) + "px"; }
}
if (typeof window !== "undefined" && window.addEventListener) { window.addEventListener("resize", equalMiniCards, false); }

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
  equalMiniCards();
  if (typeof PerformanceHistory !== "undefined") { PerformanceHistory.detail(chosen); }
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
    + '<tr><th scope="row">Temp/Freq</th><td>' + temp(d.metrics_available && state === "online" ? d.temperature : null) + ' / ' + OfflineSeen.frequencyHtml(d, d.metrics_available && state === "online")
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
  if (typeof PerformanceHistory !== "undefined" && d.performance_history_supported) {
    h += '<div class="chart-section"><div class="chart-header performance-header">Performance history ' + PerformanceHistory.controls() + '</div>'
      + '<div id="performance-detail">Loading / 加载中…</div></div>';
  }

  return h + '</div>';
}

/* Preserve Device/Network selection; History loads on demand / 保留设备选择，历史按需加载。 */
function selectDashboardTab(tab) {
  var names = ["device", "network", "history"], i, active, panel, button;
  for (i = 0; i < names.length; i += 1) {
    active = names[i] === tab;
    panel = document.getElementById(names[i] + "-panel");
    button = document.getElementById("tab-" + names[i]);
    if (panel) { panel.className = active ? "" : "hidden"; }
    if (button) {
      button.className = "dashboard-tab" + (active ? " active-tab" : "");
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }
  if (tab === "device") { fitDiskLabels(); }
  if (tab === "network" && networkHistoryData) { renderNetworkPlots(); }
  if (tab === "history" && typeof PerformanceHistory !== "undefined") { PerformanceHistory.open(); }
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

/* Sort a separate Network list; index ties preserve input order on ES5 engines.
 * 仅排序 Network 副本；用原索引保证旧浏览器上的同值顺序。 */
function networkDeviceList(list) {
  var ranks = { online: 0, unknown: 1, offline: 2 };
  return list.map(function (device, index) {
    var state = networkState(device), value = null;
    if (state === "online") {
      value = historyValue(device.uptime_seconds);
      if (value !== null && value < 0) { value = null; }
    } else if (state === "offline") { value = OfflineSeen.parse(device.last_seen); }
    return { device: device, index: index, rank: ranks[state], value: value };
  }).sort(function (a, b) {
    if (a.rank !== b.rank) { return a.rank - b.rank; }
    if (a.value !== b.value) {
      if (a.value === null) { return 1; }
      if (b.value === null) { return -1; }
      return b.value - a.value;
    }
    return a.index - b.index;
  }).map(function (item) { return item.device; });
}

function renderNetworkPanels(list, sources) {
  var online = 0, offline = 0, unknown = 0, lan = 0, zerotier = 0;
  var cards = "", summary = "", i, device, state, seen, devices = networkDeviceList(list);
  var labels = { online: "ONLINE / 在线", offline: "OFFLINE / 离线", unknown: "UNKNOWN / 未知" };
  for (i = 0; i < devices.length; i += 1) {
    device = devices[i];
    state = networkState(device);
    if (state === "online") { online += 1; }
    else if (state === "offline") { offline += 1; }
    else { unknown += 1; }
    if (device.lan_ip) { lan += 1; }
    if (device.zerotier_ip) { zerotier += 1; }
    seen = OfflineSeen.parse(device.last_seen);
    cards += '<div class="network-device-card" data-network-device="' + esc(device.device_id || "") + '"><h2>' + esc(nameOf(device)) + '</h2>'
      + '<p class="network-state ' + (state === "online" ? "ok" : state === "offline" ? "bad" : "network-unknown")
      + '">' + labels[state] + '</p><dl><dt>LAN IP</dt><dd>' + esc(device.lan_ip || "—")
      + '</dd><dt>ZeroTier IP</dt><dd>' + esc(device.zerotier_ip || "—")
      + '</dd><dt>Last Seen / 最后心跳</dt><dd>' + esc(seen === null ? "—" : new Date(seen).toLocaleString()) + '</dd>';
    if (state === "online") { cards += '<dt>Uptime / 本次开机</dt><dd>' + esc(uptime(device.uptime_seconds)) + '</dd>'; }
    cards += '</dl>';
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
  loadNetworkHistory();
}

/* Role identity survives filtering / 角色样式不随筛选重排。 */
var networkStyles = {
  lan_gateway: { label: "LAN gateway / LAN 网关", color: "#1769aa", dash: "", shape: 0 },
  upstream_gateway: { label: "Upstream gateway / 上游网关", color: "#b84b00", dash: "8 4", shape: 1 },
  endpoint_a: { label: "Endpoint A / 终端 A", color: "#27864b", dash: "3 3", shape: 2 },
  endpoint_b: { label: "Endpoint B / 终端 B", color: "#7d3c98", dash: "10 3 2 3", shape: 3 },
  public_primary: { label: "Public primary / 公网主目标", color: "#a93226", dash: "12 4", shape: 4 },
  public_control: { label: "Public control / 公网对照", color: "#117864", dash: "2 4", shape: 5 }
};

function networkTime(ms) {
  var d;
  if (ms === null || typeof ms === "undefined") { return "—"; }
  d = new Date(ms);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function networkSymbol(style, x, y, size) {
  var shapes = ["M-3,0a3,3 0 1,0 6,0a3,3 0 1,0 -6,0", "M-3,-3H3V3H-3Z", "M0,-4L4,3H-4Z",
    "M0,-4L4,0L0,4L-4,0Z", "M-3,-3L3,3M-3,3L3,-3", "M-4,0H4M0,-4V4"];
  return '<path class="network-marker" transform="translate(' + x + ',' + y + ') scale(' + size + ')" d="' + shapes[style.shape] + '"/>';
}

function networkKey(role) {
  var s = networkStyles[role];
  return '<svg class="network-series-key" viewBox="0 0 40 16" aria-hidden="true" style="color:' + s.color + '"><path class="network-series" stroke-dasharray="' + s.dash + '" d="M1,8H39"/>' + networkSymbol(s, 20, 8, 1) + '</svg>';
}

function networkPointText(target, point) {
  return networkStyles[target.role].label + ' · ' + target.target + ' · Local / 本地 ' + networkTime(point.time)
    + ' · ' + num(point.loss_pct, 1) + '% · Failed / 失败 ' + point.failed_count + ' / Total / 总探测 ' + point.count
    + (networkHistoryData.granularity === "1d" ? ' · Daily summary / 日汇总（UTC 日桶）' : ' · Minute / 分钟');
}

function networkAxisTime(ms, x, anchor) {
  var d = new Date(ms), pad = function (n) { return (n < 10 ? "0" : "") + n; };
  return '<text class="network-x-tick" x="' + x + '" y="225" text-anchor="' + anchor + '">'
    + d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
    + '<tspan x="' + x + '" dy="14">' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + '</tspan></text>';
}

/* Plot and stats share bucket validity, including the intersecting UTC day.
 * 图与统计共用有效点规则；包含与时段相交的 UTC 日桶。 */
function networkChartValue(point, key, data) {
  var value = historyValue(point[key]), count = historyValue(point[key === "rtt_ms" ? "success_count" : "count"]),
    gap = data.granularity === "1d" ? 86400000 : 60000;
  if (value === null || value < 0 || (key === "loss_pct" && value > 100) || count === null || count <= 0
      || point.time + gap <= data.start || point.time >= data.end) { return null; }
  return value;
}

function networkRangeStats(target, key, data) {
  var result = { count: 0, max: null, min: null, average: null }, sum = 0, weight = 0, i, point, value;
  if (!target) { return result; }
  for (i = 0; i < target.rows.length; i += 1) {
    point = target.rows[i]; value = networkChartValue(point, key, data);
    if (value === null) { continue; }
    result.count += 1;
    result.max = result.max === null ? value : Math.max(result.max, value);
    result.min = result.min === null ? value : Math.min(result.min, value);
    if (key === "rtt_ms") { sum += value * point.success_count; weight += point.success_count; }
    else { sum += point.failed_count; weight += point.count; }
  }
  if (weight > 0) { result.average = sum / weight * (key === "loss_pct" ? 100 : 1); }
  return result;
}

function networkStatsHtml(id) {
  var state = networkCharts[id], role = state.hover || state.pinned, target = null, data = networkHistoryData, i, stats,
    unit = state.key === "rtt_ms" ? " ms" : "%";
  for (i = 0; i < data.targets.length; i += 1) {
    if (data.targets[i].role === role && networkSelected[role]) { target = data.targets[i]; break; }
  }
  stats = networkRangeStats(target, state.key, data);
  function value(number) { return number === null ? "—" : num(number, 2) + unit; }
  return '<span class="network-stat-target">Target / 目标 <strong>' + (target ? esc(networkStyles[role].label) : '—')
    + '</strong> · <span class="network-target-ip">' + (target ? esc(target.target) : '—') + '</span></span>'
    + '<span>Range / 时段 <strong>' + esc(data.range) + '</strong></span>'
    + '<span>Valid samples / 有效样本 <strong>' + stats.count + '</strong></span>'
    + '<span>Max / 最大 <strong>' + value(stats.max) + '</strong></span>'
    + '<span>Min / 最小 <strong>' + value(stats.min) + '</strong></span>'
    + '<span>Average / 平均 <strong>' + value(stats.average) + '</strong></span>'
    + '<small>' + (state.hover && state.hover !== state.pinned ? 'Preview / 临时查看' : 'Pinned / 固定目标')
    + ' · ' + (data.granularity === "1d" ? 'UTC daily points / UTC 日汇总点' : 'Minute points / 分钟点') + '</small>';
}

function updateNetworkStats(id) {
  var state = networkCharts[id], el = document.getElementById(id + "-stats"), buttons, i;
  if (!el) { return; }
  el.innerHTML = networkStatsHtml(id);
  el.setAttribute("data-network-stats-role", state.hover || state.pinned || "");
  buttons = document.querySelectorAll('[data-network-chart="' + id + '"][data-network-legend]');
  for (i = 0; i < buttons.length; i += 1) {
    buttons[i].setAttribute("aria-pressed", buttons[i].getAttribute("data-network-legend") === state.pinned ? "true" : "false");
  }
}

/* Delegation works for SVG paths, native legend buttons and loss records.
 * 事件委托兼容 SVG 曲线、原生图例按钮和丢包记录。 */
function networkChartTarget(node) {
  var role = null, id = null, token;
  while (node && node.getAttribute) {
    token = node.getAttribute("data-network-point");
    role = role || node.getAttribute("data-network-legend") || node.getAttribute("data-network-series") || (token && token.split(':')[0]);
    id = id || node.getAttribute("data-network-chart") || (token && "network-loss-chart");
    node = node.parentNode;
  }
  return role && networkSelected[role] && networkCharts[id] ? { id: id, role: role } : null;
}

function previewNetworkTarget(node, pin) {
  var target = networkChartTarget(node), state;
  if (!target) { return false; }
  state = networkCharts[target.id];
  if (pin) { state.pinned = target.role; }
  state.hover = pin ? null : target.role;
  updateNetworkStats(target.id);
  return true;
}

function restoreNetworkTarget(event) {
  var from = networkChartTarget(event.target), to = networkChartTarget(event.relatedTarget);
  if (!from || (to && from.id === to.id && from.role === to.role)) { return; }
  networkCharts[from.id].hover = to && from.id === to.id ? to.role : null;
  updateNetworkStats(from.id);
}

function drawNetworkChart(id, key, title, unit, group) {
  var el = document.getElementById(id), data = networkHistoryData, roles = [], i, j, target, points, max = 0,
    paths = "", markers = "", legend = "", axes = "", p, x, y, previous, d, s, gap, token, detail, seriesMarkers, newSegment,
    width = Math.max(280, (el.clientWidth || 620) - 18), left = 64, right = width - 16, top = 24, bottom = 204, valid = 0,
    state = networkCharts[id], hasPinned = false;
  if (!data) { el.innerHTML = ""; return; }
  for (i = 0; i < data.targets.length; i += 1) {
    target = data.targets[i];
    if (networkStyles[target.role] && networkSelected[target.role] && (!group || (target.role.indexOf("public_") === 0 ? "public" : "private") === group)) {
      roles.push(target); if (target.role === state.pinned) { hasPinned = true; }
    }
  }
  if (!hasPinned) { state.pinned = roles.length ? roles[0].role : null; }
  state.hover = null;
  for (i = 0; i < roles.length; i += 1) {
    points = roles[i].rows;
    for (j = 0; j < points.length; j += 1) { p = networkChartValue(points[j], key, data); if (p !== null && p > max) { max = p; } }
  }
  max = key === "loss_pct" ? 100 : Math.max(1, Math.ceil(max * 1.1));
  gap = data.granularity === "1d" ? 86400000 : 60000;
  for (i = 0; i <= 4; i += 1) {
    y = bottom - i / 4 * (bottom - top);
    axes += '<path class="network-axis" d="M' + left + ',' + y + 'H' + right + '"/><text class="network-y-tick" x="' + (left - 8) + '" y="' + (y + 4) + '" text-anchor="end">' + num(max * i / 4, key === "loss_pct" ? 0 : 1) + ' ' + unit + '</text>';
  }
  for (i = 0; i < roles.length; i += 1) {
    target = roles[i]; points = target.rows; previous = null; d = ""; seriesMarkers = ""; s = networkStyles[target.role];
    legend += '<button type="button" data-network-chart="' + id + '" data-network-legend="' + target.role + '" aria-pressed="' + (state.pinned === target.role ? 'true' : 'false') + '">' + networkKey(target.role) + esc(s.label) + '</button>';
    paths += '<g data-network-chart="' + id + '" data-network-series="' + target.role + '" style="color:' + s.color + '">';
    for (j = 0; j < points.length; j += 1) {
      p = networkChartValue(points[j], key, data);
      if (p === null) { previous = null; continue; }
      valid += 1;
      x = left + (Math.max(points[j].time, data.start) - data.start) / (data.end - data.start) * (right - left);
      y = bottom - p / max * (bottom - top);
      newSegment = previous === null || points[j].time - previous > gap * 1.5;
      d += (newSegment ? " M" : " L") + x.toFixed(1) + ',' + y.toFixed(1);
      previous = points[j].time;
      if (key === "loss_pct" && p > 0) {
        token = target.role + ':' + j; detail = esc(networkPointText(target, points[j]));
        markers += '<g class="network-loss-point" data-network-point="' + token + '" tabindex="0" role="button" aria-pressed="false" aria-label="' + detail + '" style="color:' + s.color + '"><title>' + detail + '</title><circle class="network-hit" cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="12"/>' + networkSymbol(s, x.toFixed(1), y.toFixed(1), 1.5) + '</g>';
      } else if (key === "rtt_ms" && (newSegment || j % Math.max(1, Math.ceil(points.length / 24)) === 0 || j === points.length - 1)) {
        seriesMarkers += networkSymbol(s, x.toFixed(1), y.toFixed(1), 1);
      }
    }
    paths += '<path class="network-series-hit" d="' + d + '"/><path class="network-series" stroke-dasharray="' + s.dash + '" d="' + d + '"><title>' + esc(s.label + ' · ' + target.target) + '</title></path>' + seriesMarkers + '</g>';
  }
  el.innerHTML = '<h3>' + title + ' (' + unit + ')</h3><div class="network-chart-legend">' + legend + '</div><svg viewBox="0 0 ' + width + ' 250" role="group" aria-label="' + title + '">'
    + axes + networkAxisTime(data.start, left, "start") + networkAxisTime(data.end, right, "end") + paths + markers + '</svg>'
    + '<div id="' + id + '-stats" class="network-chart-stats" data-network-stats-role="' + (state.pinned || '') + '" role="status" aria-live="polite">' + networkStatsHtml(id) + '</div>'
    + '<p class="network-note">Hover to preview; click a curve or legend to pin / 悬停临时查看，点曲线或图例固定。</p>'
    + '<p class="network-note">' + (roles.length ? valid ? 'Local time / 本地时间 · ' + (data.granularity === "1d" ? 'UTC daily weighted summaries / UTC 日汇总，按探测次数加权' : 'Minute samples; gaps stay open / 分钟样本，缺测断线') : 'No samples in this range / 此时段无样本' : 'Select targets in this group / 请勾选本组目标') + '</p>';
}

function renderNetworkPlots() {
  var records = [], html = "", i, j, t, point;
  drawNetworkChart("network-rtt-private-chart", "rtt_ms", "Private RTT / 私网往返延迟", "ms", "private");
  drawNetworkChart("network-rtt-public-chart", "rtt_ms", "Public RTT / 公网往返延迟", "ms", "public");
  drawNetworkChart("network-loss-chart", "loss_pct", "Packet loss / 丢包率", "%", null);
  for (i = 0; i < networkHistoryData.targets.length; i += 1) {
    t = networkHistoryData.targets[i]; if (!networkSelected[t.role] || !networkStyles[t.role]) { continue; }
    for (j = 0; j < t.rows.length; j += 1) {
      point = t.rows[j];
      if (point.loss_pct > 0 && point.time + (networkHistoryData.granularity === "1d" ? 86400000 : 60000) > networkHistoryData.start && point.time < networkHistoryData.end) {
        records.push({ target: t, point: point, token: t.role + ':' + j });
      }
    }
  }
  records.sort(function (a, b) { return b.point.time - a.point.time || a.token.localeCompare(b.token); });
  for (i = 0; i < records.length; i += 1) {
    t = records[i]; html += '<li><button type="button" data-network-point="' + t.token + '" aria-pressed="false">' + networkKey(t.target.role) + esc(networkPointText(t.target, t.point)) + '</button></li>';
  }
  document.getElementById("network-loss-records").innerHTML = html ? '<ol>' + html + '</ol>' : '<p class="network-note">No nonzero loss records for selected targets / 所选目标无非零丢包记录。</p>';
  document.getElementById("network-point-detail").innerHTML = 'Hover or select a loss point / 悬停或点选丢包点查看记录。';
}

function renderNetworkHistory(data) {
  var cards = "", checks = "", events = "", i, t, latest, rtt, loss, selected, s;
  if (!data || data.status !== "ok") { return; }
  networkHistoryData = data;
  for (i = 0; i < data.targets.length; i += 1) {
    t = data.targets[i]; s = networkStyles[t.role]; if (!s) { continue; }
    latest = t.latest_sample;
    if (typeof networkSelected[t.role] === "undefined") { networkSelected[t.role] = true; }
    selected = networkSelected[t.role];
    rtt = latest && historyValue(latest.rtt_ms) !== null ? num(latest.rtt_ms, 2) + ' ms' : '—';
    loss = latest && historyValue(latest.loss_pct) !== null ? num(latest.loss_pct, 1) + '%' : '—';
    cards += '<article data-network-card="' + t.role + '" class="network-quality-card' + (selected ? '' : ' network-unselected') + '" style="border-top-color:' + s.color + '"><h4>' + networkKey(t.role) + esc(s.label) + '</h4><span class="network-target-ip">' + esc(t.target) + '</span><strong>Latest minute RTT / 最新分钟 ' + rtt + '</strong><span>Latest loss / 最新丢包 ' + loss + '</span><small>Local / 本地 ' + esc(networkTime(latest && latest.time)) + '</small><span>Peak / 时段丢包峰值 ' + (historyValue(t.peak_loss_pct) === null ? '—' : num(t.peak_loss_pct, 1) + '%') + (data.granularity === "1d" ? ' · Daily summary / 日汇总' : '') + '</span><small>' + esc(data.range) + (selected ? ' · Shown / 已显示' : ' · Hidden / 已隐藏') + '</small></article>';
    checks += '<label><input type="checkbox" data-network-target="' + t.role + '"' + (selected ? ' checked' : '') + '> ' + networkKey(t.role) + esc(s.label) + ' · ' + esc(t.target) + '</label>';
  }
  for (i = 0; i < data.events.length; i += 1) {
    t = data.events[i];
    events += '<tr><td>' + esc(t.kind === "target_anomaly" ? "Target anomaly / 目标异常" : t.kind === "suspected_public_connectivity" ? "Suspected public outage / 疑似公网故障" : t.kind) + '</td><td>' + esc(networkTime(t.started)) + '</td><td>' + esc(t.recovered ? networkTime(t.recovered) : "Ongoing / 进行中") + '</td><td>' + esc((t.duration_ms / 3600000).toFixed(1)) + ' h</td></tr>';
  }
  cards = cards.replace(/(<article data-network-card="endpoint_b"[\s\S]*?)(<\/article>)/, '$1<div id="endpoint-b-controls" class="endpoint-b-controls"></div>$2');
  document.getElementById("network-quality-cards").innerHTML = cards || '<p>No archived network data / 暂无网络归档数据。</p>';
  if (typeof renderEndpointB === "function") { renderEndpointB(); }
  document.getElementById("network-targets").innerHTML = checks;
  document.getElementById("network-granularity").innerHTML = data.schema_version < 3 ? "No v3 network archive yet / 尚无 v3 网络归档" : data.granularity === "1d" ? "UTC daily weighted summaries; peaks are daily / UTC 日汇总（按探测次数加权），峰值为日汇总峰值" : "UTC minute records / UTC 分钟记录";
  document.getElementById("network-events").innerHTML = events ? '<table><thead><tr><th>Event / 事件</th><th>Started / 开始</th><th>Recovered / 恢复</th><th>Duration / 持续</th></tr></thead><tbody>' + events + '</tbody></table>' : '<p>No events / 暂无故障事件。</p>';
  renderNetworkPlots();
}

function showNetworkPoint(node) {
  var token, parts, i, t, p, matches;
  while (node && node.getAttribute) {
    token = node.getAttribute("data-network-point"); if (token) { break; } node = node.parentNode;
  }
  if (!token || !networkHistoryData) { return false; }
  parts = token.split(':');
  for (i = 0; i < networkHistoryData.targets.length; i += 1) {
    t = networkHistoryData.targets[i];
    if (t.role === parts[0] && networkSelected[t.role]) {
      p = t.rows[Number(parts[1])]; if (!p) { return false; }
      document.getElementById("network-point-detail").innerHTML = esc(networkPointText(t, p));
      matches = document.querySelectorAll('[data-network-point]');
      for (i = 0; i < matches.length; i += 1) { matches[i].setAttribute("aria-pressed", matches[i].getAttribute("data-network-point") === token ? "true" : "false"); }
      return true;
    }
  }
  return false;
}


function loadNetworkHistory() {
  if (!document.getElementById("network-quality")) { return; }
  var x = new XMLHttpRequest(); networkHistoryRequest = x;
  x.onreadystatechange = function () {
    if (x.readyState !== 4 || networkHistoryRequest !== x) { return; }
    if (x.status >= 200 && x.status < 300) {
      try { renderNetworkHistory(JSON.parse(x.responseText)); } catch (e) { document.getElementById("network-events").innerHTML = "Unable to read history / 历史读取失败。"; }
    } else { document.getElementById("network-events").innerHTML = "History unavailable / 历史暂不可用。"; }
  };
  x.open("GET", "/api/history/v3/network?range=" + encodeURIComponent(networkRange), true); x.timeout = 15000; x.onerror = x.ontimeout = function () { if (networkHistoryRequest === x) { document.getElementById("network-events").innerHTML = "History unavailable / 历史暂不可用。"; } }; x.send(null);
}

if (document.addEventListener) { document.addEventListener("change", function (event) {
  var target = event.target, role;
  if (target && target.getAttribute && target.getAttribute("data-network-target")) {
    role = target.getAttribute("data-network-target"); networkSelected[role] = target.checked;
    renderNetworkHistory(networkHistoryData);
  }
}, false); }
if (document.addEventListener) { document.addEventListener("click", function (event) {
  previewNetworkTarget(event.target, true);
  if (showNetworkPoint(event.target)) { return; }
  var range = event.target && event.target.getAttribute && event.target.getAttribute("data-network-range"), buttons, i;
  if (!range) { return; }
  networkRange = range; buttons = document.querySelectorAll("[data-network-range]");
  for (i = 0; i < buttons.length; i += 1) { buttons[i].setAttribute("aria-pressed", buttons[i].getAttribute("data-network-range") === range ? "true" : "false"); }
  loadNetworkHistory();
}, false); }

if (document.addEventListener) {
  document.addEventListener("mouseover", function (event) { previewNetworkTarget(event.target, false); showNetworkPoint(event.target); }, false);
  document.addEventListener("mouseout", restoreNetworkTarget, false);
  document.addEventListener("focusin", function (event) { previewNetworkTarget(event.target, false); showNetworkPoint(event.target); }, false);
  document.addEventListener("focusout", restoreNetworkTarget, false);
  document.addEventListener("keydown", function (event) {
    if (event.keyCode === 13 || event.keyCode === 32) {
      var selected = previewNetworkTarget(event.target, true), point = showNetworkPoint(event.target);
      if (selected || point) { event.preventDefault(); }
    }
  }, false);
}
if (typeof window !== "undefined" && window.addEventListener) {
  window.addEventListener("resize", function () { if (networkHistoryData) { renderNetworkPlots(); } }, false);
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
  OfflineSeen.sync(data.server_time);
  appendHistory(list);
  latestDashboardData = { devices: list, sources: data.sources };
  document.getElementById("device-count").innerHTML = list.length;

  if (data.sources && data.sources.metrics_status === "ok") {
    document.getElementById("metrics-status").innerHTML = '<span class="ok">ONLINE</span>';
  } else {
    document.getElementById("metrics-status").innerHTML = '<span class="bad">UNAVAILABLE</span>';
  }

  if (typeof PerformanceHistory !== "undefined") { PerformanceHistory.devices(list); }
  renderDevicePanels(list);
  renderNetworkPanels(list, data.sources);
  document.getElementById("dashboard-error").className = "error hidden";
  acceptFreshness(data);
  updateFreshness();
}

/* Source timestamps are Unix seconds, never browser refresh times. */
var freshness = null;
function monotonicTime() {
  return typeof window !== "undefined" && window.performance && window.performance.now
    ? window.performance.now() : null;
}
function acceptFreshness(data) {
  var stamp = data.data_updated_at, server = data.server_time;
  if (typeof stamp !== "number" || typeof server !== "number" || !isFinite(stamp)
      || !isFinite(server) || stamp <= 0 || server < stamp || server > 8640000000000) {
    return; /* Unknown time cannot reset a known observation. */
  }
  if (freshness && stamp < freshness.stamp) { return; } /* Late responses cannot rewind. */
  freshness = {stamp: stamp, age: (server - stamp) * 1000,
    wall: new Date().getTime(), mono: monotonicTime(), elapsed: 0};
}
function updateFreshness() {
  var element = document.getElementById("last-updated"), elapsed, mono, age;
  if (!freshness) { element.innerHTML = "Updated: —"; return; }
  mono = monotonicTime();
  elapsed = Math.max(0, new Date().getTime() - freshness.wall);
  if (mono !== null && freshness.mono !== null) {
    elapsed = Math.max(elapsed, mono - freshness.mono);
  }
  freshness.elapsed = Math.max(freshness.elapsed, elapsed);
  age = freshness.age + freshness.elapsed;
  element.innerHTML = "Updated: " + esc(new Date(freshness.stamp * 1000).toLocaleString())
    + (age > 30 * 60000 ? ' <strong class="stale-warning">已断开更新 '
      + Math.floor(age / 60000) + ' 分钟</strong>' : "");
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
if (document.getElementById("tab-history")) { document.getElementById("tab-history").onclick = function () { selectDashboardTab("history"); }; }

loadHistory();
loadDashboard();
setInterval(loadDashboard, REFRESH_MS);
setInterval(loadHistory, HISTORY_REFRESH_MS);
setInterval(updateFreshness, 1000);
if (document.addEventListener) { document.addEventListener("visibilitychange", updateFreshness, false); }
if (typeof window !== "undefined") { window.addEventListener("pageshow", updateFreshness, false); }

/* Re-measure after rotation or tab changes / 旋转或标签切换后重新测量。 */
if (typeof window !== "undefined") { window.addEventListener("resize", fitDiskLabels, false); }
