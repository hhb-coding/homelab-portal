/* Full dashboard tab regression tests without a server / 无需服务器的完整仪表盘标签回归测试。 */
(function () {
  "use strict";
  var fs = require("fs"), vm = require("vm"), elements = {}, requests = [], timers = [];
  function element(id) {
    if (!elements[id]) {
      elements[id] = { innerHTML: "", className: "", attributes: {},
        setAttribute: function (key, value) { this.attributes[key] = value; } };
    }
    return elements[id];
  }
  element("network-panel").className = "hidden";
  function XHR() { requests.push(this); }
  XHR.prototype.open = function (method, url) { this.url = url; };
  XHR.prototype.send = function () {};
  function exercise() {
    var checks = 0;
    function assert(condition, message) {
      checks += 1;
      if (!condition) { throw new Error(message); }
    }
    function reply(status, body) {
      var request = requests[requests.length - 1];
      request.status = status;
      request.responseText = typeof body === "string" ? body : JSON.stringify(body);
      request.readyState = 4;
      request.onreadystatechange();
    }
    var data = { status: "ok", sources: { metrics_status: "ok" }, devices: [
      { device_id: "test-a", display_name: "Alpha", beszel_status: "up", metrics_available: true,
        cpu_percent: 10, memory_percent: 20, load_1: 0.25, lan_ip: "192.0.2.10", last_seen: "2026-01-01 00:00:00" },
      { device_id: "test-b", display_name: "Beta", beszel_status: "down", zerotier_ip: "198.51.100.10" },
      { device_id: "test-c", display_name: "<script>bad</script>", lan_ip: '<img src=x onerror="bad()">' }
    ] };
    assert(document.getElementById("tab-network").onclick, "Network button wired");
    assert(document.getElementById("network-panel").className === "hidden", "Device is default view");
    document.getElementById("tab-network").onclick();
    assert(document.getElementById("device-panel").className === "hidden", "Hide Device Details before data arrives");
    reply(200, data);
    assert(document.getElementById("network-panel").className === "", "Refresh preserves active Network tab");
    var summary = document.getElementById("network-summary").innerHTML;
    assert(summary.indexOf('Devices / 设备总数</span><strong>3') >= 0, "Count all devices");
    assert(summary.indexOf('Online / 在线</span><strong>1') >= 0, "Count online");
    assert(summary.indexOf('Offline / 离线</span><strong>1') >= 0, "Count offline");
    assert(summary.indexOf('Unknown / 未知</span><strong>1') >= 0, "Count unknown separately");
    assert(summary.indexOf('LAN IP reported / 已上报</span><strong>2 / 3') >= 0, "Count reported LAN addresses");
    assert(summary.indexOf('ZeroTier IP reported / 已上报</span><strong>1 / 3') >= 0, "Count reported overlay addresses");
    var cards = document.getElementById("network-devices").innerHTML;
    assert(cards.indexOf("&lt;script&gt;") >= 0 && cards.indexOf("<img") < 0, "Escape network names and IPs");
    assert(cards.indexOf("LAN address unavailable") >= 0, "Missing LAN handling");
    assert(cards.indexOf("No ZeroTier address reported") >= 0, "Optional ZeroTier handling");
    var count = requests.length;
    document.getElementById("tab-device").onclick();
    assert(document.getElementById("network-panel").className === "hidden", "Hide Network on Device tab");
    assert(document.getElementById("device-panel").className === "", "Show Device Details");
    assert(document.getElementById("tab-device").attributes["aria-pressed"] === "true", "Accessible selected state");
    assert(document.getElementById("mini-devices").innerHTML.indexOf("Alpha") >= 0, "Mini cards preserved");
    selectDeviceCard({ getAttribute: function () { return "test-b"; } });
    var details = document.getElementById("devices").innerHTML;
    assert(details.indexOf("Beta") >= 0, "Select device details");
    document.getElementById("tab-network").onclick();
    document.getElementById("tab-device").onclick();
    assert(selectedDeviceId === "test-b" && document.getElementById("devices").innerHTML === details, "Retain selected device across switches");
    assert(requests.length === count, "Tab switching creates no requests");
    selectDeviceCard({ getAttribute: function () { return "test-a"; } });
    render(data);
    assert(document.getElementById("devices").innerHTML.indexOf("<svg") >= 0, "Device SVG charts preserved");
    document.getElementById("tab-network").onclick();
    loadDashboard(); reply(500, {});
    assert(document.getElementById("network-devices").innerHTML === cards, "API error retains network cards");
    assert(document.getElementById("dashboard-error").innerHTML.indexOf("stale") >= 0, "Stale-data warning");
    loadDashboard(); reply(200, "broken JSON");
    assert(document.getElementById("dashboard-error").className === "error", "Malformed JSON handled");
    loadDashboard(); reply(200, { status: "error", devices: [] });
    assert(document.getElementById("network-devices").innerHTML === cards, "Error payload cannot clear valid data");
    loadDashboard(); requests[requests.length - 1].ontimeout();
    assert(document.getElementById("dashboard-error").className === "error", "Timeout handled");
    data.sources.metrics_status = "unavailable";
    data.devices = [{ device_id: "test-unknown", lan_ip: "192.0.2.20" }];
    loadDashboard(); reply(200, data);
    assert(document.getElementById("network-summary").innerHTML.indexOf("Beszel status unavailable") >= 0, "Beszel outage explained");
    assert(document.getElementById("network-devices").innerHTML.indexOf("192.0.2.20") >= 0, "Registry survives metrics outage");
    assert(document.getElementById("dashboard-error").className === "error hidden", "Recovery clears error");
    data.devices = [];
    render(data);
    assert(document.getElementById("network-summary").innerHTML.indexOf('Devices / 设备总数</span><strong>0') >= 0, "Empty counts");
    assert(document.getElementById("network-devices").innerHTML.indexOf("No devices registered") >= 0, "Empty network view");
    document.getElementById("tab-device").onclick();
    assert(document.getElementById("devices").innerHTML.indexOf("No devices registered") >= 0, "Empty Device view");
    assert(timers.length === 4 && timers[1].delay === 5000 && timers[2].delay === 60000, "Existing polling unchanged");
    assert(requests.every(function (request) {
      return request.url.indexOf("/api/dashboard?") === 0 || request.url.indexOf("/api/history?") === 0
        || request.url.indexOf("/api/history/v3/network?range=1h") === 0;
    }), "No extra network APIs");
    assert(num(null, 1) === "—" && num("", 1) === "—" && num("  ", 1) === "—" && num(false, 1) === "—" && num(Infinity, 1) === "—", "Missing and invalid numbers are not zero");
    assert(num(0, 1) === "0.0", "Real zero remains zero");
    assert(historyValue(false) === null && historyValue(Infinity) === null, "Invalid chart samples remain gaps");
    assert(metric("CPU", null).indexOf("—%") < 0 && metric("CPU", null).indexOf('class="fill"') < 0, "Missing metric has no percent or filled bar");
    assert(miniCard({device_id: "unknown", metrics_available: true}).indexOf("UNKNOWN") >= 0, "Unknown Mini Card status");
    assert(card({device_id: "unknown"}).indexOf("UNKNOWN") >= 0, "Unknown Device Details status");
    assert(miniCard({device_id: "partial", metrics_available: true}).indexOf("—%") < 0, "Missing mini metrics have no percent");
    assert(chartBox("CPU", [null, null], 100, "%").indexOf("—%") < 0, "Missing chart value has no percent");
    render({status: "ok", sources: {metrics_status: "ok"}, devices: [null, [], "bad", {device_id: "partial", beszel_status: "up", metrics_available: true}]});
    assert(document.getElementById("device-count").innerHTML === 1, "Malformed entries do not hide valid device");
    assert(document.getElementById("devices").innerHTML.indexOf("partial") >= 0, "Partial device details render");
    document.getElementById("tab-network").onclick();
    document.getElementById("tab-device").onclick();
    assert(selectedDeviceId === "partial", "Tab switch uses sanitized records");
    // Network ordering must not change Device, History or the caller's array.
    // Network 只排序副本，Device、History 与调用者的数组保持原顺序。
    var five = [
      {device_id: "off-old", display_name: "Offline old", beszel_status: "down", last_seen: "2026-01-01 12:00:00", uptime_seconds: 999999},
      {device_id: "up-short", display_name: "Online short", beszel_status: "up", uptime_seconds: 3600, lan_ip: "192.0.2.10", zerotier_ip: "198.51.100.10", last_seen: "2026-01-01 14:00:00"},
      {device_id: "unknown", display_name: "Unknown", uptime_seconds: 999999},
      {device_id: "off-new", display_name: "Offline new", beszel_status: "paused", last_seen: "2026-01-01T08:00:00-05:00"},
      {device_id: "up-long", display_name: "Online long", beszel_status: "up", uptime_seconds: 172800}
    ];
    var inputOrder = five.map(function (d) { return d.device_id; }).join(",");
    Object.freeze(five);
    assert(networkDeviceList(five).map(function (d) { return d.device_id; }).join(",") === "up-long,up-short,unknown,off-new,off-old", "Status, uptime and timezone-aware heartbeat ordering");
    assert(five.map(function (d) { return d.device_id; }).join(",") === inputOrder, "Frozen input is unchanged");
    render({status: "ok", sources: {metrics_status: "ok"}, devices: five});
    assert(latestDashboardData.devices.map(function (d) { return d.device_id; }).join(",") === inputOrder, "Shared dashboard list keeps input order");
    var mini = document.getElementById("mini-devices").innerHTML;
    assert(mini.indexOf("Offline old") < mini.indexOf("Online short"), "Device mini cards keep input order");
    cards = document.getElementById("network-devices").innerHTML;
    var cardIds = [], match, pattern = /data-network-device="([^"]+)"/g;
    while ((match = pattern.exec(cards))) { cardIds.push(match[1]); }
    assert(cardIds.join(",") === "up-long,up-short,unknown,off-new,off-old", "Rendered Network cards use the sorted copy");
    function networkCard(id) { return cards.split('data-network-device="' + id + '">')[1].split('</div>')[0]; }
    assert(networkCard("up-long").indexOf('Uptime / 本次开机</dt><dd>2d 0h') >= 0, "Online cards show current boot uptime");
    assert(networkCard("up-short").indexOf('Uptime / 本次开机</dt><dd>1h 0m') >= 0, "Reuse uptime formatting");
    assert(networkCard("off-old").indexOf("Uptime") < 0 && networkCard("unknown").indexOf("Uptime") < 0, "Offline and unknown cards omit stale uptime");
    assert(networkCard("up-short").indexOf("192.0.2.10") >= 0 && networkCard("up-short").indexOf("198.51.100.10") >= 0, "Both address fields remain visible");
    assert(networkCard("up-short").indexOf(new Date(Date.UTC(2026, 0, 1, 14)).toLocaleString()) >= 0, "SQLite UTC heartbeat displays in local time");
    assert(networkCard("off-new").indexOf(new Date(Date.UTC(2026, 0, 1, 13)).toLocaleString()) >= 0, "Offset heartbeat displays in local time");
    assert(networkCard("unknown").indexOf('Last Seen / 最后心跳</dt><dd>—') >= 0, "Missing heartbeat remains unavailable");
    var missingUptimes = [null, undefined, "", "  ", false, -1, Infinity, NaN, {}];
    var partial = missingUptimes.map(function (value, i) { return {device_id: "missing-" + i, beszel_status: "up", uptime_seconds: value}; });
    partial.push({device_id: "zero", beszel_status: "up", uptime_seconds: 0});
    partial.push({device_id: "positive", beszel_status: "up", uptime_seconds: "60"});
    var sorted = networkDeviceList(partial);
    assert(sorted[0].device_id === "positive" && sorted[1].device_id === "zero", "Finite uptime and real zero sort before unavailable values");
    assert(sorted.slice(2).every(function (d, i) { return d === partial[i]; }), "Unavailable uptimes keep stable order at the online tail");
    renderNetworkPanels(partial, {metrics_status: "ok"});
    cards = document.getElementById("network-devices").innerHTML;
    assert(networkCard("zero").indexOf('Uptime / 本次开机</dt><dd>0m') >= 0, "Real zero uptime is not missing");
    missingUptimes.forEach(function (value, i) {
      assert(networkCard("missing-" + i).indexOf('Uptime / 本次开机</dt><dd>—') >= 0, "Unavailable uptime placeholder " + i);
    });
    var missingTimes = [null, undefined, "", "invalid", "2026-02-30 12:00:00"];
    var offlineCases = missingTimes.map(function (value, i) { return {device_id: "time-" + i, beszel_status: "down", last_seen: value}; });
    offlineCases.push({device_id: "seen", beszel_status: "paused", last_seen: "2026-01-01 12:00:00"});
    offlineCases.push({device_id: "unknown-state", beszel_status: "new-status", last_seen: "2025-01-01 00:00:00"});
    offlineCases.push({device_id: "online-missing", beszel_status: "up"});
    sorted = networkDeviceList(offlineCases);
    assert(sorted.slice(0, 3).map(function (d) { return d.device_id; }).join(",") === "online-missing,unknown-state,seen", "Missing online uptime still precedes unknown and paused/offline groups");
    assert(sorted.slice(3).every(function (d, i) { return d === offlineCases[i]; }), "Missing or invalid heartbeat sorts last without reordering ties");
    renderNetworkPanels(offlineCases, {metrics_status: "ok"});
    cards = document.getElementById("network-devices").innerHTML;
    missingTimes.forEach(function (value, i) {
      assert(networkCard("time-" + i).indexOf('Last Seen / 最后心跳</dt><dd>—') >= 0, "Unavailable heartbeat placeholder " + i);
    });
    var ties = [{device_id: "up-a", beszel_status: "up", uptime_seconds: 60}, {device_id: "up-b", beszel_status: "up", uptime_seconds: 60},
      {device_id: "unknown-a"}, {device_id: "unknown-b"}, {device_id: "off-a", beszel_status: "down", last_seen: "2026-01-01 12:00:00"},
      {device_id: "off-b", beszel_status: "down", last_seen: "2026-01-01T07:00:00-05:00"}];
    assert(networkDeviceList(ties).every(function (d, i) { return d === ties[i]; }), "All groups have deterministic ties on legacy sort engines");
    console.log("Network tab behavior: " + checks + " assertions passed");
  }
  vm.runInNewContext(fs.readFileSync("static/offline-seen.js", "utf8") + "\n" + fs.readFileSync("static/dashboard.js", "utf8") + "\n(" + exercise.toString() + ")();", {
    document: { getElementById: element }, XMLHttpRequest: XHR, requests: requests, timers: timers,
    setInterval: function (callback, delay) { timers.push({ callback: callback, delay: delay }); }, console: console
  });
}());
