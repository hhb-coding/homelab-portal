'use strict';
// A timer archives a batch: its last minute can fail even when earlier new minutes responded.
function hasEvidence(endpoint, savedAt, ip) {
  if (!endpoint || endpoint.mapping_status !== 'active' || endpoint.target !== ip || !endpoint.latest_sample) return false;
  const latest = endpoint.latest_sample, rows = endpoint.rows || [];
  return latest.time > savedAt && latest.count > 0
    && rows.some(p => p.time === latest.time && p.count === latest.count && p.success_count === latest.success_count)
    && rows.some(p => p.time > savedAt && p.success_count > 0);
}
module.exports = {hasEvidence};
