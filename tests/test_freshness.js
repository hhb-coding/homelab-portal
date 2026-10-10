var fs = require('fs'), vm = require('vm'), assert = require('assert');
var wall = Date.UTC(2026, 0, 2, 0, 10), mono = 0, elements = {}, events = {}, timers = [];
function Clock(value) { return new Date(arguments.length ? value : wall); }
function XHR() {}
XHR.prototype.open = XHR.prototype.send = function () {};
var c = {Date: Clock, XMLHttpRequest: XHR,
  document: {getElementById: function (id) { return elements[id] || (elements[id] = {setAttribute: function () {}}); },
    addEventListener: function (name, cb) { events[name] = cb; }},
  window: {performance: {now: function () { return mono; }}, addEventListener: function (name, cb) { events[name] = cb; }},
  setInterval: function (cb, delay) { timers.push({cb: cb, delay: delay}); }};
vm.createContext(c); vm.runInContext(fs.readFileSync("static/offline-seen.js", "utf8") + "\n" + fs.readFileSync('static/dashboard.js', 'utf8'), c);
function text() { c.updateFreshness(); return elements['last-updated'].innerHTML; }
function sample(age) { c.acceptFreshness({data_updated_at: wall / 1000 - age * 60, server_time: wall / 1000}); }
[29, 30, 31].forEach(function (age) {
  c.freshness = null; sample(age);
  assert.strictEqual(text().indexOf('已断开更新') >= 0, age > 30);
});
assert(text().indexOf('31 分钟') >= 0);
c.fail(); wall += 60000; mono += 60000;
timers.filter(function (t) { return t.delay === 1000; }).slice(-1)[0].cb();
assert(elements['last-updated'].innerHTML.indexOf('32 分钟') >= 0);
sample(0); assert(text().indexOf('已断开更新') < 0);
wall += 31 * 60000; mono += 31 * 60000; events.pageshow();
assert(text().indexOf('31 分钟') >= 0); events.visibilitychange();
var retained = c.freshness;
[null, '', false, NaN, Infinity, -1, wall / 1000 + 1].forEach(function (v) {
  c.acceptFreshness({data_updated_at: v, server_time: wall / 1000});
  assert.strictEqual(c.freshness, retained);
});
c.acceptFreshness({data_updated_at: retained.stamp - 1, server_time: wall / 1000});
assert.strictEqual(c.freshness, retained);
c.freshness = null; assert.strictEqual(text(), 'Updated: —');
// Server time anchors age even when browser clock is years ahead.
c.acceptFreshness({data_updated_at: 100000, server_time: 100000 + 29 * 60});
assert(text().indexOf('已断开更新') < 0);
wall -= 86400000; mono += 2 * 60000;
assert(text().indexOf('31 分钟') >= 0);
// Timestamp crosses UTC midnight; elapsed arithmetic does not use time-of-day strings.
c.freshness = null;
c.acceptFreshness({data_updated_at: Date.UTC(2026, 0, 1, 23, 40) / 1000,
  server_time: Date.UTC(2026, 0, 2, 0, 11) / 1000});
assert(text().indexOf('31 分钟') >= 0);
var css = fs.readFileSync('static/style.css', 'utf8');
assert(/td:first-child \{ width:180px; white-space:nowrap;/.test(css));
assert(/@media screen and \(max-width:600px\) \{\s*\.network-device-card table,[\s\S]*display:block; width:auto; box-sizing:border-box;/.test(css));
assert(/\.network-device-card td:last-child \{ overflow-wrap:break-word; word-wrap:break-word;/.test(css));
console.log('Freshness: thresholds, failure, recovery, midnight, invalid times, clock skew, resume and responsive CSS passed');
