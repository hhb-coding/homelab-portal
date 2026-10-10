/* Full and Lite share real ES5 parsing and clocks; no browser/server required. */
var fs = require('fs'), vm = require('vm'), assert = require('assert');
function harness(view) {
  var wall = Date.UTC(2030, 0, 1), mono = 0, elements = {}, requests = [], timers = [], events = {};
  function Clock(value) { return new Date(arguments.length ? value : wall); }
  Clock.UTC = Date.UTC;
  function element(id) { return elements[id] || (elements[id] = {innerHTML: '', setAttribute: function () {}}); }
  function XHR() { requests.push(this); }
  XHR.prototype.open = XHR.prototype.send = function () {};
  var context = {Date: Clock, XMLHttpRequest: XHR,
    document: {getElementById: element, addEventListener: function (name, cb) { events[name] = cb; },
      querySelectorAll: function (selector) {
        if (selector !== '.offline-seen') { return []; }
        var parent = element(view === 'full' ? 'mini-devices' : 'lite-devices');
        var items = [], pattern = /<span class="offline-seen" data-last-seen="([^"]*)"[^>]*>[^<]*<\/span>/g, match;
        while ((match = pattern.exec(parent.innerHTML))) {
          (function (value, original) {
            var node = {getAttribute: function () { return value; }};
            Object.defineProperty(node, 'textContent', {set: function (text) {
              parent.innerHTML = parent.innerHTML.replace(original, original.replace(/>[^<]*<\/span>$/, '>' + text + '</span>'));
            }});items.push(node);
          }(match[1], match[0]));
        }
        return items;
      }},
    window: {performance: {now: function () { return mono; }}, addEventListener: function (name, cb) { events[name] = cb; }},
    setInterval: function (cb, delay) { timers.push({cb: cb, delay: delay}); }};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/offline-seen.js', 'utf8') + '\n'
    + fs.readFileSync('static/' + (view === 'full' ? 'dashboard.js' : 'lite.js'), 'utf8'), context);
  function deliver(device, server) {
    var data = {status: 'ok', server_time: server, sources: {metrics_status: 'ok'}, devices: [device]};
    if (view === 'full') { context.render(data); }
    else { timers[1].cb(); var x = requests[requests.length - 1]; x.status = 200; x.responseText = JSON.stringify(data); x.readyState = 4; x.onreadystatechange(); }
  }
  return {c: context, deliver: deliver, events: events,
    html: function () { return element(view === 'full' ? 'mini-devices' : 'lite-devices').innerHTML; },
    tick: function (ms) { wall += ms; mono += ms; timers[0].cb(); },
    skew: function (ms) { wall += ms; },
    fail: function () {
      if (view === 'full') { context.fail(); }
      else { timers[1].cb(); var x = requests[requests.length - 1]; x.status = 500; x.readyState = 4; x.onreadystatechange(); }
    }};
}
function hint(html) { var m = html.match(/class="offline-seen"[^>]*>([^<]*)</);return m ? m[1] : null; }
var now = Date.UTC(2026, 0, 2, 0, 32) / 1000, result = [];
['full', 'lite'].forEach(function (view) {
  var h = harness(view), device = {device_id: 'a', beszel_status: 'down', last_seen: '2026-01-01 23:30:00'};
  h.deliver(device, now);
  assert(/OFFLINE(?: \/ 离线)?<\/span><\/span><span class="offline-seen"/.test(h.html()) || /OFFLINE \/ 离线<\/span><span class="offline-seen"/.test(h.html()));
  assert(/1h 2m ago\)$/.test(hint(h.html())));result.push(hint(h.html()));
  h.fail();h.tick(60000);assert(/1h 3m ago\)$/.test(hint(h.html())));
  h.skew(-86400000);h.tick(60000);assert(/1h 4m ago\)$/.test(hint(h.html())));
  h.tick(2 * 86400000);h.events.pageshow();h.events.visibilitychange();
  assert(/Last seen: \d{4}-\d{2}-\d{2} \d{2}:\d{2} \(2d 1h 4m ago\)/.test(hint(h.html())));
  device.beszel_status = 'up';h.deliver(device, now + 2 * 86400 + 120);assert.strictEqual(hint(h.html()), null);
  device.beszel_status = 'paused';h.deliver(device, now + 2 * 86400 + 120);assert(hint(h.html()));
  device.beszel_status = 'unknown';h.deliver(device, now + 2 * 86400 + 120);assert.strictEqual(hint(h.html()), null);
  device.beszel_status = 'down';
  [null, '', 'bad', '2026-02-30 00:00:00', '2026-01-01', '2026-01-01T25:00:00Z',
    '2026-01-01T00:00:00+24:00', '2026-01-01 00:00:00 junk', '2028-01-01 00:00:00', 123, false].forEach(function (value) {
    device.last_seen = value;h.deliver(device, now + 2 * 86400 + 120);assert.strictEqual(hint(h.html()), 'Last seen: —');
  });
  // Same observation with an explicit timezone offset is identical to SQLite UTC.
  assert.strictEqual(h.c.OfflineSeen.parse('2026-01-01T18:30:00-05:00'), h.c.OfflineSeen.parse('2026-01-01 23:30:00'));
  assert.strictEqual(h.c.OfflineSeen.parse('2026-01-01T23:30:00.123Z'), h.c.OfflineSeen.parse('2026-01-01 23:30:00') + 123);
  assert.strictEqual(h.c.OfflineSeen.parse('2025-02-29 12:00:00'), null);
  assert(h.c.OfflineSeen.parse('2024-02-29 12:00:00') !== null);
  var clock = harness(view);
  clock.c.OfflineSeen.sync(now);
  function stampAgo(seconds) { return new Date((now - seconds) * 1000).toISOString(); }
  var localMidnight = new Date(2026, 0, 2, 0, 30).getTime() / 1000;
  var midnight = harness(view);midnight.c.OfflineSeen.sync(localMidnight);
  assert(/^Last seen: 2026-01-01 23:30 \(1h 0m ago\)$/.test(midnight.c.OfflineSeen.text(new Date((localMidnight - 3600) * 1000).toISOString())));
  assert(/59m ago\)$/.test(clock.c.OfflineSeen.text(stampAgo(3599))));
  assert(/1h 0m ago\)$/.test(clock.c.OfflineSeen.text(stampAgo(3600))));
  assert(/1d 0h 0m ago\)$/.test(clock.c.OfflineSeen.text(stampAgo(86400))));
  assert.strictEqual(clock.c.OfflineSeen.text(stampAgo(-60)), 'Last seen: —');
  clock.skew(10 * 86400000);clock.c.OfflineSeen.sync(now + 1);
  assert(/1h 2m ago\)$/.test(clock.c.OfflineSeen.text('2026-01-01 23:30:00')));
  delete clock.c.window.performance;clock.skew(-20 * 86400000);
  assert(/Last seen: .*\(1h 2m ago\)$/.test(clock.c.OfflineSeen.text('2026-01-01 23:30:00')));
  var fresh = harness(view);fresh.deliver({device_id:'a', beszel_status:'down', last_seen:'2026-01-01 23:30:00'}, undefined);
  assert.strictEqual(hint(fresh.html()), 'Last seen: —');
  [null, NaN, Infinity, '1767313920', -1].forEach(function (server) { fresh.c.OfflineSeen.sync(server);assert.strictEqual(fresh.c.OfflineSeen.text('2026-01-01 23:30:00'), 'Last seen: —'); });
});
assert.strictEqual(result[0], result[1]);
console.log('Offline Last Seen: Full/Lite transitions, retained-data timer, resume, midnight, days, offsets, invalid/future times and clock skew passed');
