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
  function text(v, unit) {
    if (numeric(v) && unit === 'B/s') {
      if (v >= 1000000000) { return (v / 1000000000).toFixed(1) + ' GB/s'; }
      if (v >= 1000000) { return (v / 1000000).toFixed(1) + ' MB/s'; }
      if (v >= 1000) { return (v / 1000).toFixed(1) + ' kB/s'; }
    }
    return numeric(v) ? v.toFixed(unit === "GHz" ? 2 : 1) + " " + unit : "—"; }
  function pad(v) { return v < 10 ? '0' + v : String(v); }
  function dateText(value) {
    var t = OfflineSeen.parse(value), d, offset, sign;
    if (t === null) { return '—'; }
    d = new Date(t); offset = -d.getTimezoneOffset(); sign = offset < 0 ? '-' : '+';
    offset = Math.abs(offset);
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds())
      + ' Local (UTC' + sign + pad(Math.floor(offset / 60)) + ':' + pad(offset % 60) + ')';
  }
  function latestSample(series) {
    var latest = null, i, p, stamp;
    for (i = 0; i < series.points.length; i += 1) {
      p = series.points[i]; stamp = OfflineSeen.parse(p.last_sample);
      if (numeric(p.value) && p.count > 0 && stamp !== null && (latest === null || stamp > latest)) { latest = stamp; }
    }
    return latest === null ? '—' : dateText(new Date(latest).toISOString());
  }
  function timeAxis(start, end) {
    var html = '<div class="performance-time-axis" aria-label="Local time">', i, j, value, label;
    var dates = [], labels = [], first = new Date(start), last = new Date(end);
    var crossDate = first.getFullYear() !== last.getFullYear() || first.getMonth() !== last.getMonth() || first.getDate() !== last.getDate();
    for (i = 0; i < 3; i += 1) {
      dates[i] = new Date(start + (end - start) * i / 2);
      labels[i] = (crossDate ? pad(dates[i].getMonth() + 1) + '-' + pad(dates[i].getDate()) + ' ' : '')
        + pad(dates[i].getHours()) + ':' + pad(dates[i].getMinutes());
    }
    for (i = 0; i < 3; i += 1) {
      value = dateText(dates[i].toISOString()); label = labels[i];
      for (j = 0; j < 3; j += 1) {
        if (i !== j && labels[i] === labels[j] && dates[i].getTimezoneOffset() !== dates[j].getTimezoneOffset()) {
          label += ' ' + value.slice(value.indexOf('UTC'), -1); break;
        }
      }
      html += '<span title="' + esc(value) + '">' + esc(label) + '</span>';
    }
    return html + '</div>';
  }
  function chart(series, start, end, expanded, companion) {
    var points = series.points, i, p, value, stamp, x, y, last = null, paths = "", path = "", length = 0;
    var min = null, max = null, span, padding, peak, step, singletonX, singletonY, j, lines = companion ? [series, companion] : [series], color = "";
    function flush() {
      if (length === 1) {
        // A short vertical mark locates an isolated bucket, without inventing time coverage.
        // 孤立/部分桶仅用竖向短线定位，不制造时间覆盖或连接缺口。
        paths += '<path class="chart-isolated' + color + '" d="M' + singletonX + ',' + (singletonY - 2).toFixed(2)
          + ' V' + (singletonY + 2).toFixed(2) + '"><title>Isolated/partial bucket / 孤立或部分缺失桶</title></path>';
      } else if (path) { paths += '<path d="' + path + '" class="chart-line' + color + '"></path>'; }
      path = ""; length = 0;
    }
    for (j = 0; j < lines.length; j += 1) {
      points = lines[j].points;
      for (i = 0; i < points.length; i += 1) {
        value = points[i].value;
        if (numeric(value)) { min = min === null ? value : Math.min(min, value); max = max === null ? value : Math.max(max, value); }
      }
    }
    if (min === null) { return (expanded ? '<div class="history-plot"><div class="history-plot-area">' : '') + '<div class="chart-wait">' + (expanded ? 'No archived data / 未读取到历史数据' : 'No data / 无数据') + '</div>' + timeAxis(start, end) + (expanded ? '</div></div>' : ''); }
    if (series.metric === 'cpu_percent' || (expanded && series.unit === '%')) {
      min = 0;
      peak = Math.max(max, numeric(series.stats.peak) ? series.stats.peak : 0);
      step = peak <= 10 ? 1 : peak <= 50 ? 5 : 10;
      max = Math.min(100, Math.max(1, Math.ceil(peak * 1.1 / step) * step));
    } else {
      span = Math.max(max - min, series.unit === 'GHz' ? 0.1 : 1);
      padding = span * 0.08;
      if (max - min < span) { min -= span / 2; max += span / 2; }
      min -= padding; max += padding;
      if (series.unit === 'GHz' || series.unit === 'B/s') { min = Math.max(0, min); }
    }
    for (j = 0; j < lines.length; j += 1) {
      points = lines[j].points; last = null; color = companion ? (j ? ' history-download' : ' history-upload') : '';
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
    }
    if (expanded) {
      return '<div class="history-plot"><div class="history-y-axis" aria-label="Y axis / 坐标轴刻度">'
        + '<span>' + esc(text(max, series.unit)) + '</span><span>' + esc(text((min + max) / 2, series.unit))
        + '</span><span>' + esc(text(min, series.unit)) + '</span></div><div class="history-plot-area">'
        + '<svg class="sparkline" viewBox="0 0 300 120" preserveAspectRatio="none" role="img" aria-label="' + esc(series.label + ' ' + series.unit) + '">'
        + '<path d="M0,5 H300 M0,60 H300 M0,115 H300" class="history-reference"></path>'
        + paths + '</svg>' + timeAxis(start, end) + '</div></div>';
    }
    return '<div class="chart-axis"><span>' + esc(text(min, series.unit)) + '</span><span>' + esc(text(max, series.unit))
      + '</span></div><svg class="sparkline" viewBox="0 0 300 120" preserveAspectRatio="none">'
      + '<path d="M0,119 H300 M0,116 V120 M150,116 V120 M300,116 V120" class="chart-baseline"></path>'
      + paths + '</svg>' + timeAxis(start, end);
  }
  function charts(data, expanded) {
    var html = '<div class="chart-grid performance-grid' + (expanded ? ' history-expanded' : '') + '">', i, s, stats, companion;
    var start = OfflineSeen.parse(data.start), end = OfflineSeen.parse(data.end);
    if (!data.series || data.series.length !== (expanded ? 7 : 3) || start === null || end === null || end <= start) { throw new Error("Invalid history"); }
    for (i = 0; i < (expanded ? 6 : data.series.length); i += 1) {
      s = data.series[i]; stats = s.stats; companion = expanded && i === 5 ? data.series[6] : null;
      if (companion && (!companion.points || companion.points.length > 500 || !companion.stats || companion.unit !== s.unit)) { throw new Error("Invalid network series"); }
      if (!s.points || s.points.length > 500 || !stats) { throw new Error("Invalid series"); }
      html += '<div class="chart-box"><div class="chart-title">' + esc(companion ? "Network Traffic " + s.unit : s.label + " " + s.unit) + '</div>'
        + (companion ? '<div class="history-legend"><span class="history-upload">Upload / 上传</span> · <span class="history-download">Download / 下载</span></div>' : '')
        + chart(s, start, end, expanded, companion) + '<div class="history-stats">' + (companion ? 'Upload / 上传: ' : '') + 'Avg / 平均 ' + esc(text(stats.average, s.unit))
        + '<br>Peak / 峰值 ' + esc(text(stats.peak, s.unit)) + '<br>Valid / 有效 ' + esc(stats.count)
        + '<br>Latest archived sample source time / 最新归档样本来源时间: ' + esc(latestSample(s))
        + (companion ? '<br>Download / 下载: Avg ' + esc(text(companion.stats.average, companion.unit)) + ' · Peak ' + esc(text(companion.stats.peak, companion.unit)) + ' · Valid ' + esc(companion.stats.count) + '<br>Latest download sample / 最新下载样本: ' + esc(latestSample(companion)) : '')
        + (expanded && i === 4 ? '<br>Archived dp disk only / 仅归档 dp 对应磁盘' : '')
        + (s.sensor ? '<br>Sensor: ' + esc(s.sensor) : '') + '</div></div>';
    }
    return html + '</div><p class="history-note">' + esc(dateText(data.start) + " – " + dateText(data.end))
      + ' · ' + esc(data.bucket_seconds) + 's buckets / 桶均值；峰值取原始有效样本。缺失留空，孤立或部分缺失桶以短线标记。</p>'
      + '<p class="history-note">Page re-queries about every 60s; archive sync usually every 5 minutes; row 1 live curves update every 5s. / 页面约60秒重新查询，归档通常每5分钟增量同步，第一排5秒实时曲线变化更快。Sample source time is not archive sync execution time / 样本来源时间并非归档同步执行时间。</p>'
      + '<p class="history-note">' + esc(data.mapping_note) + '</p>';
  }
  function placeholders(message, expanded) {
    var labels = ['CPU Frequency GHz', 'CPU Usage %', 'CPU Temperature °C'], html = '<div class="chart-grid performance-grid' + (expanded ? ' history-expanded' : '') + '">', i;
    if (expanded) { labels = labels.concat(['Memory Usage %', 'Disk Usage %', 'Network Traffic']); }
    for (i = 0; i < labels.length; i += 1) {
      html += '<div class="chart-box"><div class="chart-title">' + labels[i] + '</div><div class="chart-wait">' + esc(message) + '</div></div>';
    }
    return html + '</div>';
  }
  function draw(state, target) {
    var node = el(target);
    if (!node) { return; }
    if (state.error) { node.innerHTML = placeholders(state.error, target === 'history-result'); }
    else if (state.data) { node.innerHTML = charts(state.data, target === 'history-result'); }
    else { node.innerHTML = placeholders('Loading / 加载中…', target === 'history-result'); }
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
          charts(state.data, target === 'history-result');
        }
        draw(state, target);
      } catch (e) { state.data = null; state.error = 'Invalid history response / 历史响应无效'; draw(state, target); }
    }
    xhr.onreadystatechange = function () { if (xhr.readyState === 4) { finish(false); } };
    xhr.onerror = xhr.ontimeout = function () { finish(true); };
    xhr.open('GET', '/api/history/v2/performance?device_id=' + encodeURIComponent(device)
      + (target === 'history-result' ? '&extended=1' : '') + '&start=' + encodeURIComponent(start) + '&end=' + encodeURIComponent(end), true);
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
  function localCandidates(value) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})$/.exec(value), result = [], base, t, d;
    if (!m || Number(m[1]) < 1000) { return result; }
    base = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]));
    // Enumerate possible UTC instants; local getters reject normalized dates and DST gaps.
    for (t = base - 24 * 3600000; t <= base + 24 * 3600000; t += 60000) {
      d = new Date(t);
      if (d.getFullYear() === Number(m[1]) && d.getMonth() + 1 === Number(m[2]) && d.getDate() === Number(m[3])
          && d.getHours() === Number(m[4]) && d.getMinutes() === Number(m[5])) { result.push(t); }
    }
    return result;
  }
  function parseInput(value, choice) {
    var candidates = localCandidates(value), i;
    if (candidates.length === 1) { return candidates[0]; }
    for (i = 0; i < candidates.length; i += 1) { if (String(candidates[i]) === choice) { return candidates[i]; } }
    return null;
  }
  function updateInput(id) {
    var candidates = localCandidates(el(id).value), select = el(id + '-choice'), previous = select.value, html = '', i;
    el(id + '-choice-label').className = candidates.length > 1 ? '' : 'hidden';
    if (candidates.length > 1) {
      html = '<option value="">Choose occurrence / 选择重复时刻</option>';
      for (i = 0; i < candidates.length; i += 1) {
        html += '<option value="' + candidates[i] + '">' + (i === 0 ? 'First / 第一次 ' : 'Second / 第二次 ')
          + esc(dateText(new Date(candidates[i]).toISOString())) + '</option>';
      }
    }
    select.innerHTML = html; select.value = previous;
    el(id + '-offset').innerHTML = candidates.length === 1 ? esc(dateText(new Date(candidates[0]).toISOString()))
      : candidates.length ? 'Ambiguous Local time / 当地时间重复，请选择' : 'Invalid or nonexistent Local time / 无效或不存在的当地时间';
  }
  function setupInput(id, stamp) {
    var input = el(id), d = new Date(stamp);
    // Unsupported datetime-local implementations fall back to a plain text field.
    if (input.type !== 'datetime-local') { input.type = 'text'; }
    input.value = d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
      + (input.type === 'datetime-local' ? 'T' : ' ') + pad(d.getHours()) + ':' + pad(d.getMinutes());
    input.oninput = input.onchange = function () { el(id + '-choice').value = ''; updateInput(id); };
    el(id + '-choice').onchange = function () {
      var value = parseInput(input.value, this.value);
      el(id + '-offset').innerHTML = value === null ? 'Choose occurrence / 请选择' : esc(dateText(new Date(value).toISOString()));
    };
    updateInput(id);
  }
  function queryPage() {
    var range, start, end, device = el('history-device').value;
    pageState.version += 1;
    if (pageState.xhr && pageState.xhr.abort) { pageState.xhr.abort(); }
    pageState.xhr = null;
    if (!device) { el('history-result').innerHTML = 'No supported devices / 无支持的设备'; return; }
    if (el('history-range').value === 'custom') {
      updateInput('history-start'); updateInput('history-end');
      start = parseInput(el('history-start').value, el('history-start-choice').value);
      end = parseInput(el('history-end').value, el('history-end-choice').value);
      if (start === null || end === null || end <= start || end-start > 180*86400000) {
        el('history-result').innerHTML = 'Invalid, nonexistent or ambiguous Local range / 当地时间无效、不存在或重复未选择（最长180天）'; return;
      }
      range = [new Date(start).toISOString(), new Date(end).toISOString()];
    } else { range = preset(Number(el('history-range').value)); }
    request(pageState, 'history-result', device, range[0], range[1]);
  }
  function open() { if (!pageOpened) { pageOpened = true; queryPage(); } }
  setupInput('history-start', new Date().getTime() - 86400000);
  setupInput('history-end', new Date().getTime());
  el('history-form').onsubmit = function (event) { if (event && event.preventDefault) { event.preventDefault(); } queryPage(); return false; };
  el('history-device').onchange = queryPage;
  el('history-range').onchange = function () {
    el('history-custom').className = this.value === 'custom' ? '' : 'hidden';
    if (this.value !== 'custom') { queryPage(); }
  };
  return {controls: controls, changeRange: changeRange, devices: devices, detail: detail, open: open, charts: charts, parseInput: parseInput, localCandidates: localCandidates};
}());
