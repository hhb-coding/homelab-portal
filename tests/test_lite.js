/* Browser behavior without a live server / 不依赖真实服务器的浏览器行为测试。 */
(function () {
  "use strict";
  var fs = require("fs"), vm = require("vm");
  var elements = {}, requests = [], timers = [], checks = 0;
  function assert(condition, message) {
    checks += 1;
    if (!condition) { throw new Error(message); }
  }
  function XHR() { requests.push(this); }
  XHR.prototype.open = function (method, url) { this.url = url; };
  XHR.prototype.send = function () {};
  var context = {
    document: { getElementById: function (id) {
      if (!elements[id]) { elements[id] = { innerHTML: "", className: "" }; }
      return elements[id];
    } },
    XMLHttpRequest: XHR,
    setInterval: function (callback, delay) { timers.push({ callback: callback, delay: delay }); }
  };
  vm.runInNewContext(fs.readFileSync("static/lite.js", "utf8"), context);
  function reply(status, body) {
    var request = requests[requests.length - 1];
    request.status = status;
    request.responseText = typeof body === "string" ? body : JSON.stringify(body);
    request.readyState = 4;
    request.onreadystatechange();
  }
  function data(devices) { return { status: "ok", sources: { metrics_status: "ok" }, devices: devices }; }
  assert(requests.length === 1, "Immediate dashboard request");
  assert(timers.length === 1 && timers[0].delay === 5000, "Five-second refresh only");
  timers[0].callback();
  assert(requests.length === 1, "No overlapping requests");
  reply(200, data([
    { display_name: '<script>bad</script>', beszel_status: "up", metrics_available: true,
      lan_ip: "192.0.2.10", zerotier_ip: "198.51.100.10", cpu_percent: 0,
      memory_percent: 42, disk_percent: null, load_1: 0.25 },
    { device_id: "offline-test", beszel_status: "down", metrics_available: true, cpu_percent: 99 },
    { device_id: "unlinked-test" }
  ]));
  var html = elements["lite-devices"].innerHTML;
  assert(html.indexOf("&lt;script&gt;") >= 0 && html.indexOf("<script>") < 0, "Escape untrusted names");
  assert(html.indexOf("CPU: 0.0%") >= 0, "Zero metric is valid");
  assert(html.indexOf("Disk (—) 可用—") >= 0, "Null disk metrics are missing");
  assert(html.indexOf("Load 1m / 负载: 0.25") >= 0, "Render load");
  assert(html.indexOf("ZeroTier IP:") >= 0, "Optional overlay address");
  assert(html.indexOf("OFFLINE") >= 0 && html.indexOf("99.0%") < 0, "Hide offline metrics");
  assert(html.indexOf("UNKNOWN") >= 0, "Missing status is unknown");
  timers[0].callback(); reply(500, {});
  assert(elements["lite-devices"].innerHTML === html, "Retain previous data on error");
  assert(elements["lite-error"].innerHTML.indexOf("stale") >= 0, "Warn about stale data");
  timers[0].callback(); reply(200, "broken JSON");
  assert(elements["lite-error"].className === "", "Malformed response shows error");
  timers[0].callback(); reply(200, data([]));
  assert(elements["lite-devices"].innerHTML.indexOf("No devices") >= 0, "Empty registry");
  assert(elements["lite-error"].className === "hidden", "Recover after error");
  timers[0].callback(); requests[requests.length - 1].ontimeout();
  timers[0].callback(); reply(200, { status: "ok", devices: null });
  assert(elements["lite-error"].className === "", "Invalid payload handled");
  assert(requests.every(function (request) { return request.url.indexOf("/api/dashboard?") === 0; }), "Only dashboard requested");
  timers[0].callback(); reply(200, data([null, [], "bad", {device_id: "partial", beszel_status: "up", metrics_available: true, cpu_percent: 0}]));
  assert(elements["lite-devices"].innerHTML.indexOf("partial") >= 0, "Incomplete valid device survives malformed neighbors");
  assert(elements["lite-summary"].innerHTML.indexOf("设备: 1") >= 0, "Count only valid records");
  assert(elements["lite-devices"].innerHTML.indexOf("RAM: —") >= 0 && elements["lite-devices"].innerHTML.indexOf("CPU: 0.0%") >= 0, "Missing metrics differ from zero");
  assert(elements["lite-error"].className === "hidden", "Partial data recovery clears error");
  /* Available is 100-dp, not the old used percentage / 可用比例为 100-dp，而非旧已用比例。 */
  var sample = {device_id: "disk", beszel_status: "up", metrics_available: true, capacity_unit: "GiB",
    disk_total: 99.29, disk_used: 45.4, disk_usage_percent: 45.73, disk_percent: 90,
    disk_available: 45.4 * (100 - 45.73) / 45.73, disk_available_estimated: true};
  timers[0].callback(); reply(200, data([sample]));
  assert(elements["lite-devices"].innerHTML.indexOf("Disk (99.3G) 可用≈54.3%") >= 0, "Actual filesystem total and available percentage");
  assert(elements["lite-devices"].innerHTML.indexOf("可用≈90.0%") < 0, "Do not relabel old used percentage");
  sample.disk_usage_percent = 100; sample.disk_available = 0;
  timers[0].callback(); reply(200, data([sample]));
  assert(elements["lite-devices"].innerHTML.indexOf("可用≈0.0%") >= 0, "Full disk has zero estimated availability");
  [0, null, -1, 101, "50"].forEach(function (percent) {
    sample.disk_usage_percent = percent;
    timers[0].callback(); reply(200, data([sample]));
    assert(elements["lite-devices"].innerHTML.indexOf("Disk (99.3G) 可用—") >= 0, "Invalid/missing percentage remains unknown");
  });
  sample.disk_usage_percent = 45.73; sample.disk_available_estimated = false;
  timers[0].callback(); reply(200, data([sample]));
  assert(elements["lite-devices"].innerHTML.indexOf("可用—") >= 0, "Untrusted estimate hidden");
  sample.beszel_status = "down";
  timers[0].callback(); reply(200, data([sample]));
  assert(elements["lite-devices"].innerHTML.indexOf("Disk (—) 可用—") >= 0, "Offline disk metrics hidden");
  sample.beszel_status = "up"; sample.disk_total = 953.87; sample.disk_used = 223.62;
  sample.disk_usage_percent = 23.44; sample.disk_available = 730.3902389078498; sample.disk_available_estimated = true;
  timers[0].callback(); reply(200, data([sample]));
  assert(elements["lite-devices"].innerHTML.indexOf("Disk (953.9G) 可用≈76.6%") >= 0, "Dell rounded estimate survives in Lite");
  sample.disk_usage_percent = 23.43;
  timers[0].callback(); reply(200, data([sample]));
  assert(elements["lite-devices"].innerHTML.indexOf("可用—") >= 0, "Infeasible rounding interval rejected");
  console.log("Lite browser behavior: " + checks + " assertions passed");
}());
