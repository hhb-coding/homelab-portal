/*
 * HomeLab Portal live dashboard / 动态首页
 * ES5 + XMLHttpRequest are used for old Safari / iOS 9 compatibility.
 * 为兼容旧 Safari/iOS 9，使用 ES5 与 XMLHttpRequest。
 */
var DASHBOARD_URL = "/api/dashboard";
var REFRESH_MS = 5000;

function esc(v) {
  if (v === null || v === undefined) { return ""; }
  return String(v).replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/>/g,"&gt;").replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

function num(v, digits) {
  var n;
  if (v === null || v === undefined || v === "") { return "—"; }
  n = Number(v);
  return isNaN(n) ? "—" : n.toFixed(digits);
}

function pct(v) {
  var n = Number(v);
  if (isNaN(n) || n < 0) { return 0; }
  return n > 100 ? 100 : n;
}

function metric(label, value) {
  return '<div class="metric">'
    + '<span class="mlabel">' + esc(label) + '</span>'
    + '<span class="mvalue">' + num(value,1) + '%</span>'
    + '<span class="bar"><span class="fill" style="width:' + pct(value) + '%"></span></span>'
    + '</div>';
}

function uptime(seconds) {
  var s, d, h, m;
  if (seconds === null || seconds === undefined) { return "—"; }
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
  if (v === null || v === undefined || isNaN(n) || n <= 0) { return "—"; }
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

function card(d) {
  var online = d.beszel_status === "up";
  var h = '<div class="card">';
  h += '<div class="title"><h2>' + esc(nameOf(d)) + '</h2>'
    + '<b class="' + (online ? "ok" : "bad") + '">'
    + (online ? "ONLINE" : "OFFLINE") + '</b></div>';

  h += '<table><tr><td>LAN IP</td><td>' + esc(d.lan_ip || "—") + '</td></tr>'
    + '<tr><td>ZeroTier</td><td>' + esc(d.zerotier_ip || "—") + '</td></tr>'
    + '<tr><td>Last Seen</td><td>' + localTime(d.last_seen) + '</td></tr></table>';

  if (d.metrics_available === true) {
    h += '<div class="metrics">' + metric("CPU",d.cpu_percent)
      + metric("RAM",d.memory_percent) + metric("Disk",d.disk_percent) + '</div>';
    h += '<table><tr><td>Load 1m</td><td>' + num(d.load_1,2) + '</td></tr>'
      + '<tr><td>Load 5m</td><td>' + num(d.load_5,2) + '</td></tr>'
      + '<tr><td>Temperature</td><td>' + temp(d.temperature) + '</td></tr>'
      + '<tr><td>Uptime</td><td>' + esc(uptime(d.uptime_seconds)) + '</td></tr></table>';
  } else {
    h += '<div class="unavailable">Beszel metrics unavailable</div>';
  }

  return h + '</div>';
}

function render(data) {
  var list = data.devices || [], h = "", i;
  document.getElementById("device-count").innerHTML = list.length;

  if (data.sources && data.sources.metrics_status === "ok") {
    document.getElementById("metrics-status").innerHTML = '<span class="ok">ONLINE</span>';
  } else {
    document.getElementById("metrics-status").innerHTML = '<span class="bad">UNAVAILABLE</span>';
  }

  if (list.length === 0) {
    h = '<div class="loading">No devices registered.</div>';
  } else {
    for (i = 0; i < list.length; i = i + 1) { h += card(list[i]); }
  }

  document.getElementById("devices").innerHTML = h;
  document.getElementById("dashboard-error").className = "error hidden";
  document.getElementById("last-updated").innerHTML =
    "Updated: " + new Date().toLocaleTimeString();
}

function fail() {
  document.getElementById("dashboard-error").className = "error";
  document.getElementById("dashboard-error").innerHTML =
    "Refresh failed. Existing data remains on screen.";
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
  x.send(null);
}

loadDashboard();
setInterval(loadDashboard, REFRESH_MS);
