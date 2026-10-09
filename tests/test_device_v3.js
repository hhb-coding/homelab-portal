/* V3 data, layout and segment regressions / V3 数据、布局与横条区段回归测试。 */
(function () {
  "use strict";
  var fs = require("fs"), vm = require("vm"), assert = require("assert");
  var elements = {}, labels = [], resize;
  function element(id) {
    return elements[id] || (elements[id] = {innerHTML: "", className: "", setAttribute: function () {}});
  }
  function XHR() {}
  XHR.prototype.open = XHR.prototype.send = function () {};
  var c = {document: {getElementById: element, querySelectorAll: function () { return labels; }},
    XMLHttpRequest: XHR, setInterval: function () {},
    window: {addEventListener: function (name, callback) { resize = callback; }}};
  vm.createContext(c);
  vm.runInContext(fs.readFileSync("static/dashboard.js", "utf8"), c);
  [null, undefined, "", "  ", false, {}, [], NaN, Infinity, -1].forEach(function (v) {
    assert.strictEqual(c.capacity(v), "—");
  });
  assert.strictEqual(c.capacity(0), "0.0G");
  assert.strictEqual(c.capacity(8), "8.0G");
  assert.strictEqual(c.capacity(1024), "1.0T");
  assert.strictEqual(c.capacity(1536), "1.5T");
  var device = {device_id: "a", display_name: "Alpha", beszel_status: "up", metrics_available: true,
    lan_ip: "192.0.2.10", zerotier_ip: "198.51.100.20", last_seen: "2026-01-01 15:15:00",
    uptime_seconds: 1188000, temperature: 64, load_1: 1.3, load_5: 1.16,
    cpu_percent: 26.1, memory_percent: 52.4, memory_total: 8, disk_total: 116.34,
    disk_used: 52.94, disk_available: null, disk_usage_percent: 47.96, disk_percent: 20, capacity_unit: "GiB"};
  var mini = c.miniCard(device), details = c.card(device);
  assert(mini.indexOf("RAM (8.0G)") >= 0 && mini.indexOf("52.4%") >= 0);
  assert(mini.indexOf("DISK (116.3G)</span><b>—") >= 0);
  assert.strictEqual((mini.match(/<div><span>/g) || []).length, 4);
  assert(mini.indexOf("ONLINE") >= 0 && mini.indexOf('data-device="a"') >= 0);
  var table = details.match(/<table class="device-info">[\s\S]*?<\/table>/)[0];
  var rows = table.match(/<tr>[\s\S]*?<\/tr>/g);
  assert.strictEqual(rows.length, 3);
  rows.forEach(function (row) { assert.strictEqual((row.match(/<(?:th|td)[ >]/g) || []).length, 4); });
  assert(rows[0].indexOf("LAN IP") >= 0 && rows[0].indexOf("ZeroTier") >= 0);
  assert(rows[1].indexOf("Last Seen") >= 0 && rows[1].indexOf("Uptime") >= 0);
  assert(rows[2].indexOf("64.0 °C") >= 0 && rows[2].indexOf("1.30 / 1.16") >= 0);
  assert(/^\d{2}:\d{2}:\d{2}$/.test(c.seenTime(device.last_seen)));
  assert.strictEqual(c.seenTime(null), "—");
  var bar = c.diskMetric(device);
  assert(bar.indexOf("47.96%") >= 0 && bar.indexOf("48.0%") >= 0);
  assert(bar.indexOf("52.9G") >= 0 && bar.indexOf("63.4G") < 0); // No total-used / 不伪造可用容量
  device.disk_available = 52.94 * (100 - 47.96) / 47.96;
  device.disk_available_estimated = true;
  assert(c.diskMetric(device).indexOf('class="disk-label">USED: 52.9G</span>') >= 0);
  assert(c.diskMetric(device).indexOf('class="disk-label">FREE: 57.4G</span>') >= 0);
  assert(c.diskMetric(device).indexOf('FREE: ≈') < 0);
  assert(c.miniCard(device).indexOf('DISK (116.3G)</span><b>57.4G') >= 0);
  assert(c.miniCard(device).indexOf("≈") < 0);
  var dell = {device_id: "dell", metrics_available: true, capacity_unit: "GiB",
    disk_total: 953.87, disk_used: 223.62, disk_usage_percent: 23.44,
    disk_available: 730.3902389078498, disk_available_estimated: true};
  assert(c.miniCard(dell).indexOf('DISK (953.9G)</span><b>730.4G') >= 0);
  assert(c.diskMetric(dell).indexOf('class="disk-label">FREE: 730.4G') >= 0);
  dell.disk_usage_percent = 23.43;
  assert.strictEqual(c.capacityOf(dell, "disk_available"), "—");
  assert(c.card(device).indexOf("not exact statvfs availability") >= 0);
  device.disk_available_estimated = false;
  assert.strictEqual(c.capacityOf(device, "disk_available"), "—");
  device.disk_available_estimated = true;
  device.disk_usage_percent = 100;
  device.disk_available = 0;
  assert.strictEqual(c.capacityOf(device, "disk_available"), "≈0.0G");
  assert(c.diskMetric(device).indexOf('class="disk-label">FREE: 0.0G') >= 0);
  device.disk_usage_percent = 0;
  assert.strictEqual(c.capacityOf(device, "disk_available"), "—");
  device.disk_usage_percent = 47.96;
  [null, -1, Infinity, NaN, 1000].forEach(function (available) {
    device.disk_available = available;
    assert.strictEqual(c.capacityOf(device, "disk_available"), "—");
  });
  device.disk_available = 57.44;
  var large = {metrics_available: true, capacity_unit: "GiB", disk_total: 2048,
    disk_used: 1024, disk_usage_percent: 50, disk_available: 1024, disk_available_estimated: true};
  assert.strictEqual(c.capacityOf(large, "disk_available"), "≈1.0T");
  [0, 100, 0.01, 99.99, null, -1, 101, Infinity, NaN].forEach(function (percent) {
    device.disk_usage_percent = percent;
    var html = c.diskMetric(device);
    assert(!/NaN|Infinity|width:-/.test(html));
    assert(html.indexOf('class="disk-label">USED: ') >= 0 && html.indexOf('class="disk-label">FREE: ') >= 0);
    assert(html.indexOf('FREE: ≈') < 0);
  });
  device.disk_usage_percent = 50;
  device.disk_used = 200;
  assert(c.diskMetric(device).indexOf('width:0%') >= 0);
  device.disk_used = 52.94;
  device.capacity_unit = "GB";
  assert.strictEqual(c.capacityOf(device, "disk_total"), "—");
  device.capacity_unit = "GiB";
  device.metrics_available = false;
  assert(c.miniCard(device).indexOf("RAM (—)") >= 0);
  device.metrics_available = true;
  labels.push({style: {}, offsetWidth: 40, parentNode: {clientWidth: 0}},
    {style: {}, offsetWidth: 40, parentNode: {clientWidth: 30}},
    {style: {}, offsetWidth: 40, parentNode: {clientWidth: 100}});
  c.fitDiskLabels();
  assert.strictEqual(labels[0].style.visibility, "hidden");
  assert.strictEqual(labels[1].style.visibility, "hidden");
  assert.strictEqual(labels[2].style.visibility, "visible");
  labels[1].parentNode.clientWidth = 100;
  resize();
  assert.strictEqual(labels[1].style.visibility, "visible");
  labels[1].offsetWidth = 90; labels[1].parentNode.clientWidth = 100;
  c.fitDiskLabels();
  assert.strictEqual(labels[1].style.visibility, "hidden"); // Prefix needs room / 前缀也需要空间
  c.render({status: "ok", sources: {metrics_status: "ok"}, devices: [device, {device_id: "b"}]});
  c.selectDeviceCard({getAttribute: function () { return "b"; }});
  c.render({status: "ok", sources: {metrics_status: "ok"}, devices: [device, {device_id: "b"}]});
  assert.strictEqual(c.selectedDeviceId, "b");
  c.installHistory({devices: [{device_id: "a", points: [{timestamp: "one", cpu_percent: 1}, {timestamp: "two", cpu_percent: 2}]}]});
  assert(c.card(device).indexOf("Historical trends") >= 0 && c.card(device).indexOf("Live trends") >= 0);
  assert(c.card({device_id: "<script>"}).indexOf("&lt;script&gt;") >= 0);
  console.log("Device UI V3: capacity, three-row layout, disk boundaries, label fitting and trends passed");
}());
