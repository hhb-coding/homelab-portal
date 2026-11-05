# Step 7.07 — History Dashboard Enhancement

**Current status (2026-11-05): COMPLETED / 已完成。** [PR #21](https://github.com/hhb-coding/homelab-portal/pull/21) (7.07) and [PR #22](https://github.com/hhb-coding/homelab-portal/pull/22) (7.07.1) were squash-merged. The operator confirmed deployment and visual acceptance on HP. GitHub `main` at closeout: `5808ffadeee4f34c8e0092ca5768b8037e8617e3`; the same commit is the operator-reported HP production baseline. Check the host again before future operations. This internal Step is not a GitHub Release.

**历史开发基线：**7.07 基于 `b630a52a48e9523baf2c0e298dfdca365d169483`，7.07.1 基于 `432b00f893e5652ede6eea3a57bfa74afda284c3`；早期“待合并/待部署”描述仅指当时阶段。

History requests `/api/history/v2/performance` with `extended=1`. The default
response still has exactly CPU frequency (GHz), CPU usage (%) and CPU temperature
(°C), preserving Device and old clients. Extended responses append memory (%),
disk (%) and two network series (B/s), in that order: seven series form six rows.
Other `extended` values retain the default response. Existing read gate, read-only
SQLite connections, device mapping, 180-day cap, 500 bins, raw-sample statistics,
gap behavior and five-second query deadline remain in place. No schema or
collection/retention changes.

History alone uses full-width, vertically stacked charts, with upper/middle/lower
Y ticks and pale horizontal reference lines. These are automatic coordinate ticks,
not alert thresholds. All six plots use the same Local time range and labels.
Network upload is blue/solid and download orange/dashed with a concise legend;
each direction retains separate raw statistics and latest `last_sample` time.
B/s uses decimal kB/s, MB/s or GB/s in numeric labels as needed (1000-based).
Device retains its existing three-chart layout, 1h/6h/24h controls and refresh.
Local pickers, UTC conversion, DST gaps/occurrences, 24h/7d/30d/Custom, ES5/XHR/SVG
and the old Safari text fallback are retained. The 7.07 cache version was `707-expanded-history`; current 7.07.1 assets use `7071-device-y-axis`.

## Archive field contract

Before implementation, bounded read-only indexed queries inspected three latest
`stats_json` records per mapped HP/X230 device, exposing only structural summaries.
Both devices had valid numeric `mp`, `dp` and two-integer `b` arrays. A subsequent
bounded check of latest three stats/frequency samples confirmed all six chart
metrics valid in that small sample on both devices; this is not a coverage claim.

`mp` and `dp` are percentages. Disk means only the disk represented by archived
`dp`; it does not aggregate all HP disks or `efs`. Beszel's pinned v0.21.0
[Stats definitions](https://github.com/henrygd/beszel/blob/v0.21.0/internal/entities/system/system.go)
and [network implementation](https://github.com/henrygd/beszel/blob/v0.21.0/agent/network.go)
confirm `b[0]` is upload and `b[1]` download in bytes per second, not cumulative
bytes. Production compose identifies Beszel 0.21.0. No additional archive query or
collector is needed for the extra metrics.

Missing, nonnumeric, boolean, nonfinite, negative network, or out-of-range percent
values become null. `b` must be a two-element array; each direction is validated
independently (0 through 10,000,000,000 B/s, matching the source rate bound).
No inference from legacy `ns`/`nr`, no missing-to-zero conversion, no interpolation
or synthetic production data. An absent chart shows
`No archived data / 未读取到历史数据`; one missing network direction leaves the
other visible with its own freshness/statistics.

## Validation and review checklist

- Python synthetic archive/API tests cover opt-in/default shape, values/units,
  missing and incompatible fields, independent directions, zero versus null,
  raw statistics, partial gaps, timeout cleanup, and 180-day/500-bin limits.
- Node tests cover six rows, three Y ticks, shared Local axes, reference lines,
  network legend/directions and scaled units, no-data display, Device default
  requests, cached ranges, Local/DST conversion and stale-response rejection.
- Chrome fixture tests cover History single-column/shared axes/left ticks and
  network curves at 320/375/768/1024px without overflow; retain Device layout,
  Full/Lite and DST/Custom controls checks. Fixtures use local synthetic data.
- The operator visually accepted History's six rows and Device's three left-axis charts after deployment. The production default/extended APIs returned 3/7 series for HP and X230, with real archived metrics and null gaps. One-time read-only performance checks: HP 7d about 1.06 s, X230 30d about 2.51 s (not a future performance guarantee). Native calendar-picker interaction and iOS 9 Safari text/touch fallback remain additional hardware checks; automated Chrome tests do not substitute for those.
- GitHub merge and HP deployment were separately authorized and completed. Archive schema, collectors, timers and environment were not modified; this is a historical, operator-reported acceptance record.

## Step 7.07.1 — Device Y-axis refinement (deployed / 已部署)

Based on main `432b00f893e5652ede6eea3a57bfa74afda284c3`. Device's three CPU
plots now place max/mid/min ticks on the left, with pale references at SVG
y=5/60/115 using the existing dynamic scale (coordinate ticks, not alert limits).
A Device-only 56px gutter, 10px type and explicit line height align tick centers
with the 120px SVG content, including its 1px border. GHz keeps two decimals;
%/°C keep one. Existing three-column/wrapped responsiveness, 1h/6h/24h, Local
axes, statistics and refresh remain. History markup/styles and API logic are
unchanged. Full's four related asset URLs use `7071-device-y-axis`.
Node and isolated Chrome cover values, pixel alignment, old top-tick removal,
three references, 320/375/768/1024px, History six rows, API modes, Full/Lite and
Local/DST. User accepted the Device/History visual result on 2026-11-05; native picker and iOS9 Safari touch/text fallback remain manual checks. No backend, archive schema or collector changes; [PR #22](https://github.com/hhb-coding/homelab-portal/pull/22) merged and HP application deployed with an authorized Portal-only restart.
