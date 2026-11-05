/* ES5 + XHR + SVG, no source-time interpolation / 不对来源时间插值。 */
var PerformanceHistory = (function () {
  "use strict";
  var list = [], signature = "", pageOpened = false;
  var detailState = {version: 0}, pageState = {version: 0}, detailHours = 24, currentDevice = null;
  function el(id) { return document.getElementById(id); }
  function esc(v) {
    return String(v === null || v === undefined ? "" : v).replace(/&/g, "&amp;")
      .replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function numeric(v) { return typeof v === "number" && isFinite(v); }
  function text(v, unit) { return numeric(v) ? v.toFixed(unit === "GHz" ? 2 : 1) + " " + unit : "—"; }
  function dateText(value) {
    var t = OfflineSeen.parse(value);
    return t === null ? "—" : new Date(t).toISOString().slice(0, 16).replace("T", " ");
  }
  function timeAxis(start, end) {
    var html = '<div class="performance-time-axis" aria-label="UTC time">', i, value, label;
    var dates = end - start > 6 * 3600000 || new Date(start).getUTCDate() !== new Date(end).getUTCDate();
    for (i = 0; i < 3; i += 1) {
      value = new Date(start + (end - start) * i / 2).toISOString();
      label = dates ? value.slice(5, 10) + ' ' + value.slice(11, 16) : value.slice(11, 16);
      html += '<span title="' + esc(dateText(value) + ' UTC') + '">' + esc(label) + '</span>';
    }
    return html + '</div>';
  }
  function chart(series, start, end) {
    var points = series.points, i, p, value, stamp, x, y, last = null, paths = "", path = "", length = 0;
    var min = null, max = null, span, padding, peak, step, singletonX, singletonY;
    function flush() {
      if (length === 1) {
        // A short vertical mark locates an isolated bucket, without inventing time coverage.
        // 孤立/部分桶仅用竖向短线定位，不制造时间覆盖或连接缺口。
        paths += '<path class="chart-isolated" d="M' + singletonX + ',' + (singletonY - 2).toFixed(2)
          + ' V' + (singletonY + 2).toFixed(2) + '"><title>Isolated/partial bucket / 孤立或部分缺失桶</title></path>';
      } else if (path) { paths += '<path d="' + path + '" class="chart-line"></path>'; }
      path = ""; length = 0;
    }
    for (i = 0; i < points.length; i += 1) {
      value = points[i].value;
      if (numeric(value)) { min = min === null ? value : Math.min(min, value); max = max === null ? value : Math.max(max, value); }
    }
    if (min === null) { return '<div class="chart-wait">No data / 无数据</div>' + timeAxis(start, end); }
    if (series.metric === 'cpu_percent') {
      min = 0;
      peak = Math.max(max, numeric(series.stats.peak) ? series.stats.peak : 0);
      step = peak <= 10 ? 1 : peak <= 50 ? 5 : 10;
      max = Math.min(100, Math.max(1, Math.ceil(peak * 1.1 / step) * step));
    } else {
      span = Math.max(max - min, series.unit === 'GHz' ? 0.1 : 1);
      padding = span * 0.08;
      if (max - min < span) { min -= span / 2; max += span / 2; }
      min -= padding; max += padding;
      if (series.unit === 'GHz') { min = Math.max(0, min); }
    }
    for (i = 0; i < points.length; i += 1) {
      p = points[i]; value = p.value; stamp = OfflineSeen.parse(p.timestamp);
      if (!numeric(value) || stamp === null) { flush(); last = null; continue; }
      x = ((stamp - start) / (end - start)) * 300;
      y = 115 - (value - min) / (max - min) * 110;
      if (p.gap || last === null || last.gap) { flush(); }
      if (!length) { path = "M" + x.toFixed(2) + "," + y.toFixed(2); singletonX = x.toFixed(2); singletonY = y; }
      else { path += " L" + x.toFixed(2) + "," + y.toFixed(2); }
      length += 1; last = p;
    }
    flush();
    return '<div class="chart-axis"><span>' + esc(text(min, series.unit)) + '</span><span>' + esc(text(max, series.unit))
      + '</span></div><svg class="sparkline" viewBox="0 0 300 120" preserveAspectRatio="none">'
      + '<path d="M0,119 H300 M0,116 V120 M150,116 V120 M300,116 V120" class="chart-baseline"></path>'
      + paths + '</svg>' + timeAxis(start, end);
  }
  function charts(data) {
    var html = '<div class="chart-grid performance-grid">', i, s, stats;
    var start = OfflineSeen.parse(data.start), end = OfflineSeen.parse(data.end);
    if (!data.series || data.series.length !== 3 || start === null || end === null || end <= start) { throw new Error("Invalid history"); }
    for (i = 0; i < data.series.length; i += 1) {
      s = data.series[i]; stats = s.stats;
      if (!s.points || s.points.length > 500 || !stats) { throw new Error("Invalid series"); }
      html += '<div class="chart-box"><div class="chart-title">' + esc(s.label + " " + s.unit) + '</div>'
        + chart(s, start, end) + '<div class="history-stats">Avg / 平均 ' + esc(text(stats.average, s.unit))
        + '<br>Peak / 峰值 ' + esc(text(stats.peak, s.unit)) + '<br>Valid / 有效 ' + esc(stats.count)
        + (s.sensor ? '<br>Sensor: ' + esc(s.sensor) : '') + '</div></div>';
    }
    return html + '</div><p class="history-note">' + esc(dateText(data.start) + " – " + dateText(data.end))
      + ' UTC · ' + esc(data.bucket_seconds) + 's buckets / 桶均值；峰值取原始有效样本。缺失留空，孤立或部分缺失桶以短线标记。</p>'
      + '<p class="history-note">' + esc(data.mapping_note) + '</p>';
  }
  function placeholders(message) {
    var labels = ['CPU Frequency GHz', 'CPU Usage %', 'CPU Temperature °C'], html = '<div class="chart-grid performance-grid">', i;
    for (i = 0; i < labels.length; i += 1) {
      html += '<div class="chart-box"><div class="chart-title">' + labels[i] + '</div><div class="chart-wait">' + esc(message) + '</div></div>';
    }
    return html + '</div>';
  }
  function draw(state, target) {
    var node = el(target);
    if (!node) { return; }
    if (state.error) { node.innerHTML = placeholders(state.error); }
    else if (state.data) { node.innerHTML = charts(state.data); }
    else { node.innerHTML = placeholders('Loading / 加载中…'); }
  }
  function request(state, target, device, start, end) {
    var version, xhr;
    state.version += 1; version = state.version;
    if (state.xhr && state.xhr.abort) { state.xhr.abort(); }
    state.device = device; state.data = null; state.error = null; state.at = new Date().getTime();
    xhr = new XMLHttpRequest(); state.xhr = xhr; draw(state, target);
    function finish(error) {
      if (version !== state.version) { return; }
      state.xhr = null;
      try {
        if (error || xhr.status < 200 || xhr.status >= 300) {
          state.error = 'History unavailable or disabled / 历史不可用或未启用';
        } else {
          state.data = JSON.parse(xhr.responseText);
          charts(state.data);
        }
        draw(state, target);
      } catch (e) { state.data = null; state.error = 'Invalid history response / 历史响应无效'; draw(state, target); }
    }
    xhr.onreadystatechange = function () { if (xhr.readyState === 4) { finish(false); } };
    xhr.onerror = xhr.ontimeout = function () { finish(true); };
    xhr.open('GET', '/api/history/v2/performance?device_id=' + encodeURIComponent(device)
      + '&start=' + encodeURIComponent(start) + '&end=' + encodeURIComponent(end), true);
    xhr.timeout = 10000; xhr.send(null);
  }
  function preset(days) {
    var end = OfflineSeen.now(), start;
    if (end === null) { end = new Date().getTime(); }
    end = Math.floor(end / 60000) * 60000;
    start = end - days * 86400000;
    return [new Date(start).toISOString(), new Date(end).toISOString()];
  }
  function detail(device) {
    var range;
    currentDevice = device;
    if (!device || !device.performance_history_supported || !el('performance-detail')) { return; }
    if (detailState.device !== device.device_id || detailState.hours !== detailHours || (!detailState.xhr && new Date().getTime() - detailState.at > 60000)) {
      detailState.hours = detailHours;
      range = preset(detailHours / 24); request(detailState, 'performance-detail', device.device_id, range[0], range[1]);
    } else { draw(detailState, 'performance-detail'); }
  }
  function controls() {
    var hours = [1, 6, 24], html = '<label class="performance-range">Range / 范围 <select id="performance-detail-range" aria-label="Performance history range" onchange="PerformanceHistory.changeRange(this.value)">', i;
    for (i = 0; i < hours.length; i += 1) {
      html += '<option value="' + hours[i] + '"' + (hours[i] === detailHours ? ' selected="selected"' : '') + '>' + hours[i] + 'h</option>';
    }
    return html + '</select></label>';
  }
  function changeRange(value) {
    if (value !== '1' && value !== '6' && value !== '24') { return; }
    detailHours = Number(value); detail(currentDevice);
  }
  function devices(items) {
    var supported = [], i, sig, options = '', previous = el('history-device').value;
    for (i = 0; i < items.length; i += 1) { if (items[i].performance_history_supported) { supported.push(items[i]); } }
    list = supported; sig = JSON.stringify(supported.map(function (d) { return [d.device_id, d.display_name, d.hostname]; }));
    if (signature === sig) { return; }
    signature = sig;
    for (i = 0; i < list.length; i += 1) {
      options += '<option value="' + esc(list[i].device_id) + '">' + esc(list[i].display_name || list[i].hostname || list[i].device_id) + '</option>';
    }
    el('history-device').innerHTML = options;
    for (i = 0; i < list.length; i += 1) { if (list[i].device_id === previous) { el('history-device').value = previous; } }
    if (pageOpened) { queryPage(); }
  }
  function parseInput(value) {
    return /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(value) ? OfflineSeen.parse(value.replace(' ', 'T') + ':00Z') : null;
  }
  function queryPage() {
    var range, start, end, device = el('history-device').value;
    pageState.version += 1;
    if (pageState.xhr && pageState.xhr.abort) { pageState.xhr.abort(); }
    pageState.xhr = null;
    if (!device) { el('history-result').innerHTML = 'No supported devices / 无支持的设备'; return; }
    if (el('history-range').value === 'custom') {
      start = parseInput(el('history-start').value); end = parseInput(el('history-end').value);
      if (start === null || end === null || end <= start || end-start > 180*86400000) {
        el('history-result').innerHTML = 'Invalid UTC range / UTC时间范围无效（最长180天）'; return;
      }
      range = [new Date(start).toISOString(), new Date(end).toISOString()];
    } else { range = preset(Number(el('history-range').value)); }
    request(pageState, 'history-result', device, range[0], range[1]);
  }
  function open() { if (!pageOpened) { pageOpened = true; queryPage(); } }
  el('history-form').onsubmit = function (event) { if (event && event.preventDefault) { event.preventDefault(); } queryPage(); return false; };
  el('history-device').onchange = queryPage;
  el('history-range').onchange = function () {
    el('history-custom').className = this.value === 'custom' ? '' : 'hidden';
    if (this.value !== 'custom') { queryPage(); }
  };
  return {controls: controls, changeRange: changeRange, devices: devices, detail: detail, open: open, charts: charts, parseInput: parseInput};
}());
