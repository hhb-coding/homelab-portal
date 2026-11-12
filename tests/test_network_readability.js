/* Network role/point regressions with a synthetic DOM / 网络角色与点位回归。 */
(function () {
  'use strict';
  var fs = require('fs'), vm = require('vm'), assert = require('assert');
  var nodes = {}, listeners = {}, requests = [];
  function node(id) {
    return nodes[id] || (nodes[id] = { innerHTML: '', clientWidth: 980, attributes: {},
      setAttribute: function (key, value) { this.attributes[key] = value; } });
  }
  function XHR() { requests.push(this); }
  XHR.prototype.open = function (method, url) { this.url = url; };
  XHR.prototype.send = function () {};
  var context = { document: { getElementById: node, querySelectorAll: function () { return []; },
    addEventListener: function (type, callback) { (listeners[type] || (listeners[type] = [])).push(callback); } },
    XMLHttpRequest: XHR, setInterval: function () {} };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/offline-seen.js', 'utf8') + '\n' + fs.readFileSync('static/dashboard.js', 'utf8'), context);
  var end = Date.UTC(2026, 0, 31, 12), roles = Object.keys(context.networkStyles);
  function point(time, total, success, rtt) {
    return {time: time, count: total, failed_count: total - success,
      loss_pct: total ? 100 * (total - success) / total : null, rtt_ms: rtt};
  }
  var data = {status: 'ok', schema_version: 3, range: '1h', granularity: '1m', start: end - 3600000, end: end,
    events: [], targets: roles.map(function (role, i) {
      return {role: role, target: '192.0.2.' + (i + 1), latest_sample: point(end - 60000, 6, 6, 2),
        peak_loss_pct: 100 / 6, rows: [point(end - 240000, 6, 5, 2), point(end - 180000, 0, 0, null), point(end - 60000, 6, 6, 2)]};
    })};
  data.targets[2].latest_sample = null; data.targets[2].peak_loss_pct = null; data.targets[2].rows = [];
  data.targets[4].rows[0] = point(end - 240000, 6, 0, null); data.targets[4].peak_loss_pct = 100;
  context.renderNetworkHistory(data);
  var cards = node('network-quality-cards').innerHTML;
  assert(cards.includes('最新丢包 0.0%') && cards.includes('时段丢包峰值 16.7%'));
  assert(cards.includes('192.0.2.1') && cards.includes('最新分钟 —') && !cards.includes('null'));
  var privateHtml = node('network-rtt-private-chart').innerHTML, publicHtml = node('network-rtt-public-chart').innerHTML;
  assert(!privateHtml.includes('data-network-series="public_primary"') && publicHtml.includes('data-network-series="public_primary"'));
  assert(!publicHtml.includes('data-network-series="lan_gateway"'));
  assert.strictEqual((privateHtml.match(/data-network-series=/g) || []).length, 4);
  assert.strictEqual((publicHtml.match(/data-network-series=/g) || []).length, 2);
  var lossHtml = node('network-loss-chart').innerHTML;
  assert(lossHtml.includes('100 %</text>') && lossHtml.includes('0 %</text>'));
  assert(lossHtml.includes('data-network-point="public_primary:0"') && lossHtml.includes('100.0%'));
  assert(lossHtml.includes('失败 6 / Total / 总探测 6'));
  assert.strictEqual((lossHtml.match(/class="network-loss-point"/g) || []).length, 5);
  var axes = [privateHtml, publicHtml, lossHtml].map(function (html) { return html.match(/<text class="network-x-tick"[\s\S]*?<\/text>/g).join(''); });
  assert.strictEqual(axes[0], axes[1]); assert.strictEqual(axes[1], axes[2]);
  // Missing minute and null RTT must start new subpaths, never join across a gap.
  var lan = privateHtml.match(/stroke-dasharray="" d="([^"]+)"/g).pop();
  assert.strictEqual((lan.match(/ M/g) || []).length, 2); assert(!lan.includes(' L'));
  var pointNode = {getAttribute: function (key) { return key === 'data-network-point' ? 'lan_gateway:0' : null; }};
  assert(context.showNetworkPoint(pointNode));
  assert(node('network-point-detail').innerHTML.includes('192.0.2.1') && node('network-point-detail').innerHTML.includes('失败 1 / Total / 总探测 6'));
  assert(node('network-point-detail').innerHTML.includes(context.networkTime(end - 240000)));
  var prevented = false;
  listeners.keydown[0]({keyCode: 32, target: pointNode, preventDefault: function () { prevented = true; }});
  assert(prevented, 'Space selects SVG points without scrolling');
  listeners.focusin[0]({target: {getAttribute: function () { return null; }, parentNode: pointNode}});
  assert(node('network-point-detail').innerHTML.includes('失败 1 / Total / 总探测 6'));
  var keyBefore = context.networkKey('public_control'), colorBefore = context.networkStyles.public_control.color;
  context.networkSelected.lan_gateway = false; context.networkSelected.public_primary = false;
  context.renderNetworkHistory(data);
  assert(!node('network-loss-records').innerHTML.includes('data-network-point="lan_gateway:'));
  assert(!node('network-loss-chart').innerHTML.includes('data-network-series="public_primary"'));
  assert(node('network-quality-cards').innerHTML.includes('network-unselected'));
  assert.strictEqual(context.networkKey('public_control'), keyBefore);
  assert(node('network-rtt-public-chart').innerHTML.includes('style="color:' + colorBefore + '"'));
  assert(!context.showNetworkPoint(pointNode));
  // Daily summary at the intersecting UTC day boundary stays visible at the left edge.
  data.range = '7d'; data.granularity = '1d'; data.start = end - 7 * 86400000;
  data.targets[5].rows = [point(data.start - 43200000, 6000, 5000, 25)];
  context.renderNetworkHistory(data);
  assert(node('network-quality-cards').innerHTML.includes('Daily summary / 日汇总'));
  assert(node('network-quality-cards').innerHTML.includes('最新分钟 2.00 ms'));
  assert(node('network-loss-chart').innerHTML.includes('data-network-point="public_control:0"'));
  assert(node('network-loss-records').innerHTML.includes('失败 1000 / Total / 总探测 6000'));
  roles.forEach(function (role) { context.networkSelected[role] = false; });
  context.renderNetworkHistory(data);
  assert(node('network-loss-chart').innerHTML.includes('100 %</text>'));
  assert(node('network-rtt-private-chart').innerHTML.includes('请勾选本组目标'));
  assert(!node('network-loss-chart').innerHTML.includes('data-network-series='));
  // Range requests remain XHR; a late response cannot replace a newer range.
  ['1h', '24h', '7d', '30d'].forEach(function (range) {
    listeners.click.forEach(function (callback) { callback({target: {getAttribute: function (key) { return key === 'data-network-range' ? range : null; }}}); });
    assert(requests[requests.length - 1].url.endsWith('range=' + range));
  });
  var latestRequest = requests[requests.length - 1], lateRequest = requests[requests.length - 2];
  function reply(request, payload) { request.status = 200; request.readyState = 4; request.responseText = JSON.stringify(payload); request.onreadystatechange(); }
  data.range = '30d'; reply(latestRequest, data);
  var oldData = JSON.parse(JSON.stringify(data)); oldData.range = '7d'; reply(lateRequest, oldData);
  assert.strictEqual(context.networkHistoryData.range, '30d');
  // API-controlled strings are escaped in cards and accessible point descriptions.
  data.targets[5].target = '<img src=x onerror="bad()">'; context.networkSelected.public_control = true;
  context.renderNetworkHistory(data);
  assert(!node('network-quality-cards').innerHTML.includes('<img'));
  assert(!node('network-loss-chart').innerHTML.includes('<img'));
  console.log('Network readability: cards, gaps, counts, axes, filtering, daily buckets and XHR passed');
}());
