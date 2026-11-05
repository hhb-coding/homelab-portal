/* Shared ES5 Last Seen display. Heartbeat receipt is not an outage start time. */
var OfflineSeen = (function () {
  "use strict";
  var anchor = null;
  function mono() {
    return typeof window !== "undefined" && window.performance && window.performance.now
      ? window.performance.now() : null;
  }
  function sync(server) {
    if (typeof server !== "number" || !isFinite(server) || server <= 0
        || server > 8640000000000 || (anchor && server < anchor.server)) { return; }
    anchor = {server: server, wall: new Date().getTime(), mono: mono(), elapsed: 0};
  }
  function now() {
    var elapsed, current;
    if (!anchor) { return null; }
    elapsed = Math.max(0, new Date().getTime() - anchor.wall);
    current = mono();
    if (current !== null && anchor.mono !== null) { elapsed = Math.max(elapsed, current - anchor.mono); }
    anchor.elapsed = Math.max(anchor.elapsed, elapsed);
    return anchor.server * 1000 + anchor.elapsed;
  }
  function parse(value) {
    var p, date, offset = 0, stamp;
    if (typeof value !== "string") { return null; }
    p = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})?$/);
    if (!p || Number(p[1]) < 1000) { return null; }
    stamp = Date.UTC(Number(p[1]), Number(p[2]) - 1, Number(p[3]), Number(p[4]), Number(p[5]), Number(p[6]));
    date = new Date(stamp);
    if (date.getUTCFullYear() !== Number(p[1]) || date.getUTCMonth() !== Number(p[2]) - 1
        || date.getUTCDate() !== Number(p[3]) || date.getUTCHours() !== Number(p[4])
        || date.getUTCMinutes() !== Number(p[5]) || date.getUTCSeconds() !== Number(p[6])) { return null; }
    if (p[8] && p[8] !== "Z") {
      if (Number(p[8].slice(1, 3)) > 23 || Number(p[8].slice(4, 6)) > 59) { return null; }
      offset = (Number(p[8].slice(1, 3)) * 60 + Number(p[8].slice(4, 6))) * 60000;
      if (p[8].charAt(0) === "-") { offset = -offset; }
    }
    stamp += p[7] ? Number("0." + p[7]) * 1000 : 0;
    stamp -= offset;
    return isFinite(stamp) && stamp > 0 ? stamp : null;
  }
  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function text(value) {
    var stamp = parse(value), current = now(), age, minutes, date, currentDate, label, duration;
    if (stamp === null || current === null || stamp > current) { return "Last seen: —"; }
    age = current - stamp;
    minutes = Math.floor(age / 60000);
    date = new Date(stamp);
    label = pad(date.getHours()) + ":" + pad(date.getMinutes());
    currentDate = new Date(current);
    if (age >= 86400000 || date.getFullYear() !== currentDate.getFullYear()
        || date.getMonth() !== currentDate.getMonth() || date.getDate() !== currentDate.getDate()) {
      label = date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + " " + label;
    }
    duration = minutes < 60 ? minutes + "m" : minutes < 1440
      ? Math.floor(minutes / 60) + "h " + (minutes % 60) + "m"
      : Math.floor(minutes / 1440) + "d " + Math.floor(minutes % 1440 / 60) + "h " + (minutes % 60) + "m";
    return "Last seen: " + label + " (" + duration + " ago)";
  }
  function escape(value) {
    return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function html(value) {
    return '<span class="offline-seen" data-last-seen="' + escape(value)
      + '" title="Last valid heartbeat / 最后有效心跳；并非精确断线时间">' + text(value) + '</span>';
  }
  /* Frequency expiry shares the server clock and existing timer / 频率过期复用服务端时钟和现有定时器。 */
  function frequencyHtml(device, legacyAvailable) {
    var value = device.cpu_frequency_ghz, sampled = parse(device.frequency_sampled_utc), current = now();
    var valid = typeof value === "number" && isFinite(value) && value > 0;
    if (!device.frequency_freshness) { return valid && legacyAvailable ? value.toFixed(2) + " GHz" : "—"; }
    valid = valid && device.frequency_freshness === "fresh" && sampled !== null && current !== null
      && current >= sampled && current - sampled <= 120000;
    return '<span class="current-frequency" data-frequency-sampled="' + (sampled || 0)
      + '" title="' + escape((device.frequency_source || "") + " / " + (device.frequency_sampled_utc || "")
        + " / " + device.frequency_freshness) + '">' + (valid ? value.toFixed(2) + " GHz" : "—") + '</span>';
  }
  function update() {
    var items = document.querySelectorAll ? document.querySelectorAll(".offline-seen") : [], i;
    for (i = 0; i < items.length; i += 1) { items[i].textContent = text(items[i].getAttribute("data-last-seen")); }
    items = document.querySelectorAll ? document.querySelectorAll(".current-frequency") : [];
    for (i = 0; i < items.length; i += 1) {
      var sampled = Number(items[i].getAttribute("data-frequency-sampled")), current = now();
      if (!sampled || current === null || current < sampled || current - sampled > 120000) {
        items[i].textContent = "—";
        items[i].setAttribute("title", "Frequency expired or unavailable / 主频过期或不可用");
      }
    }
    if (typeof equalMiniCards === "function") { equalMiniCards(); }
  }
  setInterval(update, 1000);
  if (document.addEventListener) { document.addEventListener("visibilitychange", update, false); }
  if (typeof window !== "undefined") { window.addEventListener("pageshow", update, false); }
  return {now: now, frequencyHtml: frequencyHtml, sync: sync, parse: parse, text: text, html: html, update: update};
}());
