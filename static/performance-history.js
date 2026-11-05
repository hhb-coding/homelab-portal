/* ES5 + XHR + SVG, no source-time interpolation / 不对来源时间插值。 */
var PerformanceHistory = (function () {
  "use strict";
  var list = [], signature = "", pageOpened = false;
  var detailState = {version: 0}, pageState = {version: 0};
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
  function chart(series, start, end) {
    var points = series.points, i, p, value, stamp, x, y, last = null, paths = "", path = "", dots = "";
    var min = series.metric === "cpu_percent" ? 0 : null, max = series.metric === "cpu_percent" ? 100 : null;
    for (i = 0; i < points.length; i += 1) {
      value = points[i].value;
      if (numeric(value)) { min = min === null ? value : Math.min(min, value); max = max === null ? value : Math.max(max, value); }
    }
    if (min === null) { return '<div class="chart-wait">No data / 无数据</div>'; }
    if (max - min < 0.1) { max = min + 0.1; }
    for (i = 0; i < points.length; i += 1) {
      p = points[i]; value = p.value; stamp = OfflineSeen.parse(p.timestamp);
      if (!numeric(value) || stamp === null) {
        if (path) { paths += '<path d="' + path + '" class="chart-line"></path>'; }
        path = ""; last = null; continue;
      }
      x = ((stamp - start) / (end - start)) * 300;
      y = 115 - (value - min) / (max - min) * 110;
      /* Partial buckets are isolated; never bridge known holes / 部分缺失桶独立显示，禁止跨缺口连线。 */
      if (p.gap || last === null || (last && last.gap)) {
        if (path) { paths += '<path d="' + path + '" class="chart-line"></path>'; }
        path = "M" + x.toFixed(2) + "," + y.toFixed(2);
      } else { path += " L" + x.toFixed(2) + "," + y.toFixed(2); }
      dots += '<circle cx="' + x.toFixed(2) + '" cy="' + y.toFixed(2) + '" r="1.5" fill="#337ab7"><title>'
        + esc(dateText(p.timestamp) + " UTC: " + text(value, series.unit) + "; n=" + p.count
          + (p.gap ? "; partial / 部分缺失" : "")) + '</title></circle>';
      last = p;
    }
    if (path) { paths += '<path d="' + path + '" class="chart-line"></path>'; }
    return '<div class="chart-axis"><span>' + esc(text(min, series.unit)) + '</span><span>' + esc(text(max, series.unit))
      + '</span></div><svg class="sparkline" viewBox="0 0 300 120" preserveAspectRatio="none">' + paths + dots + '</svg>';
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
      + ' UTC · ' + esc(data.bucket_seconds) + 's buckets / 桶均值；峰值取原始有效样本。缺失留空，部分缺失桶以孤立点显示。</p>'
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
    if (!device || !device.performance_history_supported || !el('performance-detail')) { return; }
    if (detailState.device !== device.device_id || (!detailState.xhr && new Date().getTime() - detailState.at > 60000)) {
      range = preset(1); request(detailState, 'performance-detail', device.device_id, range[0], range[1]);
    } else { draw(detailState, 'performance-detail'); }
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
  return {devices: devices, detail: detail, open: open, charts: charts, parseInput: parseInput};
}());
