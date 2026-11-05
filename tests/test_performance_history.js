/* Key page regressions with a synthetic DOM / 合成 DOM 关键页面回归。 */
(function () {
  'use strict';
  process.env.TZ = 'America/Montreal';
  var fs = require('fs'), vm = require('vm'), assert = require('assert');
  var nodes = {}, requests = [], timers = [], clock = Date.UTC(2026, 0, 2), mono = 0;
  function node(id) {
    return nodes[id] || (nodes[id] = {innerHTML: '', value: '', className: '', style: {},
      setAttribute: function (k, v) { this[k] = v; }, getAttribute: function (k) { return this[k]; }});
  }
  function XHR() { requests.push(this); }
  XHR.prototype.open = function (method, url) { this.url = url; };
  XHR.prototype.send = function () {};
  XHR.prototype.abort = function () { this.aborted = true; };
  function Clock(value) { return new Date(arguments.length ? value : clock); }
  Clock.UTC = Date.UTC;
  var frequencyNodes = [];
  var c = {Date: Clock, document: {getElementById: node,
    querySelectorAll: function (selector) { return selector === '.current-frequency' ? frequencyNodes : []; }},
    window: {addEventListener: function () {}, performance: {now: function () { return mono; }}},
    setInterval: function (cb) { timers.push(cb); }, XMLHttpRequest: XHR};
  vm.createContext(c);
  ['offline-seen.js', 'performance-history.js', 'dashboard.js'].forEach(function (name) {
    vm.runInContext(fs.readFileSync('static/' + name, 'utf8'), c);
  });
  c.OfflineSeen.sync(clock / 1000);
  var device = {device_id: 'example-x230', display_name: '<X230>', performance_history_supported: true,
    cpu_frequency_ghz: 1.19, frequency_freshness: 'fresh', frequency_source: 'windows_processor_performance',
    frequency_sampled_utc: '2026-01-01T23:58:00Z', beszel_status: 'down'};
  assert(c.OfflineSeen.frequencyHtml(device, false).indexOf('1.19 GHz') >= 0, 'Frequency independent of Beszel');
  var span = node('frequency-test'); span['data-frequency-sampled'] = clock - 120000; span.textContent = '1.19 GHz';
  frequencyNodes.push(span); mono = 1; c.OfflineSeen.update();
  assert.strictEqual(span.textContent, '—', 'Expire even without successful refresh');
  assert(c.OfflineSeen.frequencyHtml(device, false).indexOf('1.19 GHz') < 0);
  function payload(id) {
    return {status: 'ok', device_id: id, start: '2026-01-01T00:00:00Z', end: '2026-01-02T00:00:00Z', bucket_seconds: 180,
      mapping_note: 'Current mapping / 当前关联', series: ['CPU Frequency', 'CPU Usage', 'CPU Temperature'].map(function (label, i) {
        return {label: label, metric: ['cpu_frequency_ghz', 'cpu_percent', 'cpu_temperature_c'][i], unit: ['GHz', '%', '°C'][i],
          stats: {average: 1, peak: 2, count: 3}, points: [
            {timestamp: '2026-01-01T00:00:00Z', value: 0, count: 1},
            {timestamp: '2026-01-01T00:03:00Z', value: null, count: 0},
            {timestamp: '2026-01-01T00:06:00Z', value: 2, count: 1},
            {timestamp: '2026-01-01T00:09:00Z', value: 1, count: 1, gap: true}]};
      })};
  }
  var html = c.PerformanceHistory.charts(payload('example-x230'));
  assert.strictEqual((html.match(/class="chart-box"/g) || []).length, 3);
  assert(html.indexOf('CPU Frequency') < html.indexOf('CPU Usage') && html.indexOf('CPU Usage') < html.indexOf('CPU Temperature'));
  assert(html.search(/ L[0-9]/) < 0, 'Null and partial buckets cannot be bridged');
  assert(html.indexOf('Avg / 平均') >= 0 && html.indexOf('Peak / 峰值') >= 0);
  assert(html.indexOf('<circle') < 0, 'No per-point circles');
  assert.strictEqual((html.match(/class="performance-time-axis"/g) || []).length, 3, 'One time axis per chart');
  var axes = html.match(/<div class="performance-time-axis"[^>]*>[\s\S]*?<\/div>/g);
  assert.strictEqual(axes[0], axes[1]); assert.strictEqual(axes[1], axes[2]);
  assert(axes[0].indexOf('2025-12-31 19:00') >= 0 && axes[0].indexOf('UTC-05:00') >= 0);
  var seasonal = payload('seasonal');
  seasonal.start = '2026-03-08T06:00:00Z'; seasonal.end = '2026-03-08T08:00:00Z';
  html = c.PerformanceHistory.charts(seasonal);
  assert(html.indexOf('01:00:00 Local (UTC-05:00)') >= 0);
  assert(html.indexOf('03:00:00 Local (UTC-04:00)') >= 0);
  seasonal.start = '2026-11-01T05:00:00Z'; seasonal.end = '2026-11-01T07:00:00Z';
  html = c.PerformanceHistory.charts(seasonal);
  assert(html.indexOf('01:00:00 Local (UTC-04:00)') >= 0);
  assert(html.indexOf('01:00:00 Local (UTC-05:00)') >= 0);
  seasonal.series.forEach(function (s, i) {
    s.points[0].last_sample = '2026-07-01T00:0' + i + ':00Z';
    s.points[1].last_sample = '2026-07-02T00:00:00Z';
  });
  html = c.PerformanceHistory.charts(seasonal);
  [0, 1, 2].forEach(function (i) { assert(html.indexOf('2026-06-30 20:0' + i + ':00 Local (UTC-04:00)') >= 0); });
  assert(html.indexOf('2026-07-01 20:00:00') < 0, 'Null values cannot supply freshness');
  html = c.PerformanceHistory.charts(payload('missing'));
  assert.strictEqual((html.match(/最新归档样本来源时间: —/g) || []).length, 3);
  assert(html.indexOf('60s') >= 0 && html.indexOf('5 minutes') >= 0);
  var low = payload('low'); low.series[1].stats.peak = 4.2;
  assert(c.PerformanceHistory.charts(low).indexOf('5.0 %') >= 0, 'Usage scales to raw peak with headroom');
  low.series[1].stats.peak = 42;
  assert(c.PerformanceHistory.charts(low).indexOf('50.0 %') >= 0, 'Raw peak, not bucket average, determines usage range');
  low.series[1].stats.peak = 100;
  assert(c.PerformanceHistory.charts(low).indexOf('100.0 %') >= 0, 'Usage maximum remains bounded');
  low.series[1].points.forEach(function (p) { p.value = 0; p.gap = false; }); low.series[1].stats.peak = 0;
  html = c.PerformanceHistory.charts(low);
  assert(html.indexOf('1.0 %') >= 0 && html.indexOf('NaN') < 0, 'Flat zero usage has valid positive scale span');
  low.series[1].points.forEach(function (p) { p.value = null; }); low.series[1].stats.peak = null;
  assert(c.PerformanceHistory.charts(low).indexOf('No data / 无数据') >= 0, 'Missing usage is not zero');
  var continuous = payload('continuous');
  continuous.series.forEach(function (s) { s.points[1].value = 1; });
  html = c.PerformanceHistory.charts(continuous);
  assert(html.search(/ L[0-9]/) >= 0 && html.indexOf('<circle') < 0, 'Continuous observations retain lines');
  assert(html.indexOf('chart-isolated') >= 0, 'Partial bucket remains a separate short mark');

  assert.strictEqual(c.PerformanceHistory.parseInput('2026-02-30 00:00'), null);
  assert.strictEqual(c.PerformanceHistory.parseInput('2026-01-01T00:00'), null);
  node('history-device').value = 'example-x230'; node('history-range').value = '7';
  c.PerformanceHistory.devices([device, {device_id: 'example-dell'}]);
  assert(node('history-device').innerHTML.indexOf('&lt;X230&gt;') >= 0);
  assert(node('history-device').innerHTML.indexOf('dell') < 0);
  c.selectDashboardTab('history');
  assert.strictEqual(node('history-panel').className, '');
  assert.strictEqual(node('device-panel').className, 'hidden');
  var first = requests[requests.length - 1];
  assert(first.url.indexOf('/api/history/v2/performance?') === 0);
  assert(decodeURIComponent(first.url).indexOf('2025-12-26') >= 0, '7d preset uses shared clock');
  node('history-device').value = 'example-hp'; node('history-device').onchange();
  var second = requests[requests.length - 1];
  first.status = 200; first.responseText = JSON.stringify(payload('old')); first.readyState = 4; first.onreadystatechange();
  assert(node('history-result').innerHTML.indexOf('Loading') >= 0, 'Ignore late result');
  second.status = 200; second.responseText = JSON.stringify(payload('example-hp')); second.readyState = 4; second.onreadystatechange();
  assert(node('history-result').innerHTML.indexOf('CPU Temperature') >= 0);
  node('history-range').value = 'custom'; node('history-range').onchange.call(node('history-range'));
  node('history-start').value = 'bad'; node('history-end').value = 'bad';
  var count = requests.length; node('history-form').onsubmit({preventDefault: function () {}});
  assert.strictEqual(requests.length, count, 'Invalid custom range makes no request');
  assert(node('history-result').innerHTML.indexOf('UTC时间范围无效') >= 0);
  node('history-start').value = '2026-01-01 00:00'; node('history-end').value = '2026-01-02 00:00';
  node('history-form').onsubmit();
  assert(decodeURIComponent(requests[requests.length - 1].url).indexOf('start=2026-01-01T00:00:00.000Z') >= 0, 'Custom input remains UTC');
  var custom = requests[requests.length - 1]; custom.status = 503; custom.readyState = 4; custom.onreadystatechange();
  assert(node('history-result').innerHTML.indexOf('未启用') >= 0);
  c.renderDevicePanels([device]);
  var detail = requests[requests.length - 1];
  detail.status = 200; detail.responseText = JSON.stringify(payload('example-x230')); detail.readyState = 4; detail.onreadystatechange();
  assert(node('devices').innerHTML.indexOf('Performance history') >= 0);
  assert.strictEqual((node('performance-detail').innerHTML.match(/class="chart-box"/g) || []).length, 3);
  count = requests.length; c.renderDevicePanels([device]); assert.strictEqual(requests.length, count, 'Reuse detail cache');
  assert(c.PerformanceHistory.controls().indexOf('value="24" selected="selected"') >= 0, 'Default detail range is 24h');
  var pendingRange;
  ['1', '6', '24'].forEach(function (hours) {
    var before = requests.length;
    c.PerformanceHistory.changeRange(hours);
    assert.strictEqual(requests.length, before + 1, 'One shared request for three charts');
    var r = requests[requests.length - 1], params = new URL('http://test'+r.url).searchParams;
    assert.strictEqual(Date.parse(params.get('end')) - Date.parse(params.get('start')), Number(hours)*3600000);
    if (pendingRange) {
      pendingRange.status = 200; pendingRange.responseText = JSON.stringify(payload('old-range'));
      pendingRange.readyState = 4; pendingRange.onreadystatechange();
      assert(node('performance-detail').innerHTML.indexOf('Loading') >= 0, 'Late range response ignored');
    }
    pendingRange = r;
    c.renderDevicePanels([device]);
    assert.strictEqual(requests.length, before + 1, 'Dashboard refresh preserves pending range');
    assert(c.PerformanceHistory.controls().indexOf('value="'+hours+'" selected="selected"') >= 0);
  });
  var rangeData = payload('example-x230');
  pendingRange.status = 200; pendingRange.responseText = JSON.stringify(rangeData); pendingRange.readyState = 4; pendingRange.onreadystatechange();
  assert(node('performance-detail').innerHTML.indexOf('<circle') < 0);
  count = requests.length; c.PerformanceHistory.changeRange('bad'); assert.strictEqual(requests.length, count);
  c.PerformanceHistory.changeRange('6');
  var other = {device_id: 'example-hp', performance_history_supported: true}; c.renderDevicePanels([other]);
  var last = requests[requests.length - 1];
  assert.strictEqual(new URL('http://test'+last.url).searchParams.get('device_id'), 'example-hp');
  assert(c.PerformanceHistory.controls().indexOf('value="6" selected="selected"') >= 0, 'Range survives device switch');

  c.selectDashboardTab('network'); assert.strictEqual(node('history-panel').className, 'hidden');
  console.log('Performance history key page regressions passed');
}());
