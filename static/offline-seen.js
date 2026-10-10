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
    var stamp = parse(value), current = now(), age, minutes, date, label, duration;
    if (stamp === null || current === null || stamp > current) { return "Last: —"; }
    age = current - stamp;
    minutes = Math.floor(age / 60000);
    date = new Date(stamp);
    label = pad(date.getHours()) + ":" + pad(date.getMinutes());
    if (age >= 86400000) {
      label = date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) + " " + label;
    }
    duration = minutes < 60 ? minutes + "m" : minutes < 1440
      ? Math.floor(minutes / 60) + "h " + pad(minutes % 60) + "m"
      : Math.floor(minutes / 1440) + "d " + pad(Math.floor(minutes % 1440 / 60)) + "h " + pad(minutes % 60) + "m";
    return "Last: " + label + " · " + duration + " ago";
  }
  function escape(value) {
    return String(value || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function html(value) {
    return '<span class="offline-seen" data-last-seen="' + escape(value)
      + '" title="Last valid heartbeat / 最后有效心跳；并非精确断线时间">' + text(value) + '</span>';
  }
  function update() {
    var items = document.querySelectorAll ? document.querySelectorAll(".offline-seen") : [], i;
    for (i = 0; i < items.length; i += 1) { items[i].textContent = text(items[i].getAttribute("data-last-seen")); }
  }
  setInterval(update, 1000);
  if (document.addEventListener) { document.addEventListener("visibilitychange", update, false); }
  if (typeof window !== "undefined") { window.addEventListener("pageshow", update, false); }
  return {sync: sync, parse: parse, text: text, html: html, update: update};
}());
