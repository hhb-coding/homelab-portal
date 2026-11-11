"""Synthetic API + temporary SQLite only / 模拟 API、临时库，不读取生产配置。"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from requests.exceptions import ConnectionError as APIConnectionError

from beszel_client import BeszelClient
from metrics_archive import ArchiveError, MountError, writer
from frequency_migration import migrate as migrate_frequency
from network_migration import migrate, TABLES
from network_archive import collect, milliseconds, load_roles, maintain, MINUTE, DAY, RETENTION

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
RUN = milliseconds(NOW)
SYSTEM = "synthetic-system"
# Documentation address ranges and synthetic short IDs / 文档网段与合成短 ID。
ROLE_TARGETS = dict(lan_gateway="192.0.2.1", upstream_gateway="198.51.100.1",
                   endpoint_a="192.0.2.2", endpoint_b="192.0.2.3",
                   public_primary="203.0.113.1", public_control="203.0.113.2")
ROLES = {"system_id": SYSTEM, "targets": ROLE_TARGETS,
         "abnormal_minutes": 3, "recovery_minutes": 2}


def monitor(identity="abc1234", target="192.0.2.1", **changes):
    return dict(id=identity, system=SYSTEM, target=target, protocol="icmp", interval=10,
                enabled=True, **changes)


def sample(index=1, when=None, identity="abc1234", total=6, success=6, response=2000):
    return dict(id=f"{index:010d}", monitor=identity, system=SYSTEM, type="1m",
                created=RUN-20*MINUTE if when is None else when,
                total_count=total, success_count=success, res_sum=success*response,
                res_min=response if success else 0, res_max=response if success else 0)


class API:
    def __init__(self, records=(), monitors=None, cap=None):
        self.records = list(records)
        self.monitors = monitors if monitors is not None else [monitor()]
        self.calls, self.monitor_calls = [], []
        self.cap, self.fail_on = cap, None

    def get_network_monitors_page(self, after, per_page):
        self.monitor_calls.append((after, per_page))
        return sorted([m for m in self.monitors if after is None or m["id"] > after],
                      key=lambda m: m["id"])[:min(per_page, self.cap or per_page)]

    def get_network_archive_page(self, identity, start, end, after, per_page):
        self.calls.append((identity, start, end, after, per_page))
        if len(self.calls) == self.fail_on:
            raise APIConnectionError("sensitive upstream response")
        records = sorted([r for r in self.records if r["monitor"] == identity
                          and start <= r["created"] <= end and
                          (after is None or (r["created"], r["id"]) > after)],
                         key=lambda r: (r["created"], r["id"]))
        return records[:min(per_page, self.cap or per_page)]


class ArchiveFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portal-network-test-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"metrics.sqlite3"
        self.guard = lambda p: Path(p)
        self.context = writer(self.path, self.guard)
        self.db = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        migrate(self.db, lambda: None)

    def count(self, table="network_samples"):
        return self.db.execute("SELECT count(*) FROM " + table).fetchone()[0]


class NetworkArchiveTests(ArchiveFixture):
    def test_short_pages_tied_ms_short_ids_fixed_upper_and_overlap(self):
        api = API([sample(i) for i in range(1, 8)], cap=1)
        report = collect(self.db, api, NOW, page_size=5)
        self.assertEqual((report["network_inserted"], report["network_failed"]), (7, 0))
        self.assertEqual(len(api.calls), 8)  # Short pages still continue to empty.
        self.assertEqual({c[2] for c in api.calls}, {RUN})
        self.assertEqual(self.db.execute("SELECT created_ms,record_id FROM network_checkpoints").fetchone(),
                         (sample()["created"], "0000000007"))
        api.records.append(sample(8, RUN-22*MINUTE))  # bounded late arrival
        api.calls.clear()
        report = collect(self.db, api, NOW, page_size=2)
        self.assertEqual((report["network_inserted"], report["network_duplicates"]), (1, 7))
        self.assertEqual(api.calls[0][1], sample()["created"]-10*MINUTE)
        self.assertEqual(self.count(), 8)
        self.assertEqual(self.db.execute("SELECT sample_count FROM network_daily").fetchone()[0], 8)

    def test_monitor_discovery_pages_and_eight_character_identity(self):
        api = API([sample(1), sample(2, identity="abc12345")],
                  [monitor(), monitor("abc12345", "192.0.2.2")], cap=1)
        report = collect(self.db, api, NOW, page_size=4)
        self.assertEqual((report["network_monitors"], report["network_inserted"]), (2, 2))
        self.assertEqual(len(api.monitor_calls), 3)

    def test_mid_run_new_record_waits_for_next_fixed_upper(self):
        api = API([sample(1), sample(2, RUN+MINUTE)])
        self.assertEqual(collect(self.db, api, NOW)["network_inserted"], 1)
        self.assertEqual(collect(self.db, api, NOW+timedelta(minutes=2))["network_inserted"], 1)

    def test_interruption_retries_committed_page_without_double_daily_count(self):
        api = API([sample(i, RUN-(22-i)*MINUTE) for i in range(1, 8)])
        api.fail_on = 2
        first = collect(self.db, api, NOW, page_size=2)
        self.assertEqual((first["network_inserted"], first["network_failed"]), (2, 1))
        saved = self.db.execute("SELECT created_ms,record_id FROM network_checkpoints").fetchone()
        self.assertEqual(saved, (RUN-20*MINUTE, "0000000002"))
        api.fail_on = None
        second = collect(self.db, api, NOW, page_size=2)
        self.assertEqual((second["network_inserted"], self.count()), (5, 7))
        self.assertEqual(self.db.execute("SELECT sample_count FROM network_daily").fetchone()[0], 7)

    def test_sample_daily_checkpoint_transaction_rolls_back(self):
        self.db.execute("""CREATE TEMP TRIGGER fail_checkpoint BEFORE INSERT ON network_checkpoints
            BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
        report = collect(self.db, API([sample(1), sample(2)]), NOW)
        self.assertEqual((report["network_failed"], report["network_inserted"]), (1, 0))
        for table in ("network_samples", "network_checkpoints", "network_daily"):
            self.assertEqual(self.count(table), 0)
        self.db.execute("DROP TRIGGER fail_checkpoint")
        self.assertEqual(collect(self.db, API([sample()]), NOW)["network_inserted"], 1)

    def test_mount_loss_at_page_commit_rolls_back(self):
        guard = Mock(side_effect=[None, None, None, MountError("synthetic mount loss")])
        with self.assertRaises(MountError):
            collect(self.db, API([sample()]), NOW, check_mount=guard)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.count("network_daily"), 0)
        self.assertEqual(self.count("network_checkpoints"), 0)

    def test_empty_does_not_create_or_advance_checkpoint(self):
        collect(self.db, API(), NOW)
        self.assertEqual(self.count("network_checkpoints"), 0)
        collect(self.db, API([sample()]), NOW)
        saved = self.db.execute("SELECT * FROM network_checkpoints").fetchall()
        collect(self.db, API(), NOW+timedelta(minutes=5))
        self.assertEqual(self.db.execute("SELECT * FROM network_checkpoints").fetchall(), saved)

    def test_failure_isolated_to_monitor(self):
        api = API([sample(1), sample(2, identity="abc12345")],
                  [monitor(), monitor("abc12345", "192.0.2.2")])
        api.fail_on = 1
        report = collect(self.db, api, NOW)
        self.assertEqual((report["network_failed"], report["network_inserted"]), (1, 1))
        self.assertEqual(self.db.execute("SELECT monitor_id FROM network_checkpoints").fetchall(), [("abc12345",)])

    def test_bad_page_is_atomic_and_error_is_sanitized(self):
        for change in ({"system": "wrong"}, {"type": "10m"}, {"created": True},
                       {"id": 123}, {"total_count": True}, {"success_count": 7},
                       {"res_sum": -1}, {"res_min": float("nan")},
                       {"res_max": 1}, {"future_field": float("nan")}):
            with self.subTest(change=change):
                bad = {**sample(2), **change}
                api = Mock()
                api.get_network_monitors_page.side_effect = [[monitor()], []]
                api.get_network_archive_page.return_value = [sample(1), bad]
                report = collect(self.db, api, NOW)
                self.assertEqual(report["network_failed"], 1)
                self.assertNotIn("sensitive", json.dumps(report))
                self.assertEqual(self.count(), 0)
                self.assertEqual(self.count("network_daily"), 0)

    def test_unordered_or_repeated_page_refused(self):
        for page in ([sample(2), sample(1)], [sample(1), sample(1)]):
            api = Mock()
            api.get_network_monitors_page.side_effect = [[monitor()], []]
            api.get_network_archive_page.return_value = page
            self.assertEqual(collect(self.db, api, NOW)["network_failed"], 1)
            self.assertEqual(self.count(), 0)
        api = Mock()
        api.get_network_monitors_page.side_effect = [[monitor()], []]
        api.get_network_archive_page.return_value = [sample(1)]
        report = collect(self.db, api, NOW)
        self.assertEqual((report["network_inserted"], report["network_failed"]), (1, 1))

    def test_conflicting_replay_preserves_original_and_totals(self):
        collect(self.db, API([sample()]), NOW)
        report = collect(self.db, API([sample(response=4000)]), NOW)
        self.assertEqual(report["network_failed"], 1)
        self.assertEqual(self.db.execute("SELECT sample_count,res_sum FROM network_daily").fetchone(), (1, 12000))

    def test_daily_probe_weighted_latency_loss_and_raw_microseconds(self):
        rows = [sample(1, total=6, success=4, response=2000),
                sample(2, RUN-19*MINUTE, total=1, success=1, response=10000)]
        collect(self.db, API(rows), NOW)
        result = self.db.execute("SELECT total_count,success_count,res_sum,res_min,res_max,avg_ms,loss_pct FROM network_daily_stats").fetchone()
        self.assertEqual(result[:6], (7, 5, 18000, 2000, 10000, 3.6))
        self.assertAlmostEqual(result[6], 200/7)
        body = json.loads(self.db.execute("SELECT raw_json FROM network_samples ORDER BY record_id LIMIT 1").fetchone()[0])
        self.assertEqual(body["res_sum"], 8000)

    def test_no_attempts_unknown_and_all_failed_latency_null(self):
        collect(self.db, API([sample(total=0, success=0)]), NOW)
        self.assertEqual(self.db.execute("SELECT avg_ms,loss_pct,res_min,res_max FROM network_daily_stats").fetchone(),
                         (None, None, None, None))
        collect(self.db, API([sample(2, RUN-19*MINUTE, total=6, success=0)]), NOW)
        self.assertEqual(self.db.execute("SELECT avg_ms,loss_pct FROM network_daily_stats").fetchone(), (None, 100))

    def test_partial_day_pruning_replay_and_clock_rollback_keep_daily_totals(self):
        boundary = RUN-RETENTION
        rows = [sample(1, boundary-1), sample(2, boundary)]
        collect(self.db, API(rows), NOW-timedelta(minutes=1))
        self.assertEqual(self.count(), 2)
        self.assertEqual(collect(self.db, API(rows), NOW)["network_pruned"], 1)
        self.assertEqual(self.count(), 1)  # exact 90-day boundary stays
        self.assertEqual(collect(self.db, API(rows), NOW+timedelta(milliseconds=1))["network_pruned"], 1)
        self.assertEqual(self.count(), 0)
        for when in (NOW+timedelta(minutes=5), NOW-timedelta(hours=1)):
            report = collect(self.db, API(rows), when)
            self.assertEqual(report["network_inserted"], 0)
        self.assertEqual(self.db.execute("SELECT sum(sample_count),sum(total_count) FROM network_daily").fetchone(), (2, 12))

    def test_prune_mount_failure_rolls_back_floor_and_records(self):
        from network_archive import prune
        collect(self.db, API([sample()]), NOW)
        before = self.db.execute("SELECT retention_floor_ms FROM network_archive_meta").fetchone()[0]
        with self.assertRaises(MountError):
            prune(self.db, RUN, Mock(side_effect=[None, MountError("mount lost")]))
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.db.execute("SELECT retention_floor_ms FROM network_archive_meta").fetchone()[0], before)


class EventTests(ArchiveFixture):
    def setUp(self):
        super().setUp()
        self.monitors = [monitor(f"m{i:07d}", target) for i, target in enumerate(ROLE_TARGETS.values())]
        self.ids = dict(zip(ROLE_TARGETS, (m["id"] for m in self.monitors)))
        self.start = RUN-30*MINUTE
        self.rows = []

    def observations(self, slot, abnormal=(), missing=(), zero=()):
        for i, role in enumerate(ROLE_TARGETS):
            if role in missing:
                continue
            self.rows.append(sample(slot*10+i+1, self.start+slot*MINUTE+35000+i,
                                    self.ids[role], total=0 if role in zero else 6,
                                    success=0 if role in zero else 5 if role in abnormal else 6))

    def run_archive(self, now=NOW):
        return collect(self.db, API(self.rows, self.monitors), now, roles=ROLES, page_size=2)

    def events(self, kind=None):
        return self.db.execute("SELECT kind,started_ms,detected_ms,recovered_ms,recovery_detected_ms FROM network_events" +
                               (" WHERE kind=?" if kind else "") + " ORDER BY kind,started_ms", (kind,) if kind else ()).fetchall()

    def test_single_public_loss_opens_target_and_recovers_once(self):
        for slot in range(3):
            self.observations(slot, ["public_primary"])
        self.assertEqual(self.run_archive()["network_correlation_ready"], 1)
        self.assertEqual(self.events(), [("target_anomaly", self.start, self.start+2*MINUTE, None, None)])
        for slot in (3, 4):
            self.observations(slot)
        self.run_archive(); self.run_archive()
        self.assertEqual(self.events(), [("target_anomaly", self.start, self.start+2*MINUTE,
                                         self.start+3*MINUTE, self.start+4*MINUTE)])

    def test_two_public_losses_same_minutes_with_upstream_healthy(self):
        for slot in range(3):
            self.observations(slot, ["public_primary", "public_control", "lan_gateway"])
        self.run_archive()
        self.assertEqual(len(self.events("target_anomaly")), 3)
        self.assertEqual(len(self.events("suspected_public_connectivity")), 1)
        # NX30 LAN failure does not replace upstream reachability / LAN 网关不充当上游。
        for slot in (3, 4):
            self.observations(slot)
        self.run_archive(); self.run_archive()
        self.assertEqual(self.events("suspected_public_connectivity")[0][3:],
                         (self.start+3*MINUTE, self.start+4*MINUTE))

    def test_upstream_unreachable_or_unknown_never_infers_public_outage(self):
        for mode in ("abnormal", "missing", "zero"):
            with self.subTest(mode=mode):
                self.rows = []
                for slot in range(3):
                    self.observations(slot, ["public_primary", "public_control"] +
                                      (["upstream_gateway"] if mode == "abnormal" else []),
                                      missing=["upstream_gateway"] if mode == "missing" else [],
                                      zero=["upstream_gateway"] if mode == "zero" else [])
                # independent database per mode avoids conflicting immutable samples
                path = Path(self.temp.name)/f"{mode}.sqlite3"
                with writer(path, self.guard) as db:
                    migrate(db, lambda: None)
                    collect(db, API(self.rows, self.monitors), NOW, roles=ROLES)
                    self.assertEqual(db.execute("SELECT count(*) FROM network_events WHERE kind='suspected_public_connectivity'").fetchone()[0], 0)

    def test_missing_minutes_break_streak_and_do_not_recover(self):
        for slot in (0, 2, 3):
            self.observations(slot, ["public_primary"])
        self.run_archive()
        self.assertEqual(self.events(), [])
        self.observations(4, ["public_primary"])
        self.run_archive()
        self.assertEqual(self.events()[0][1], self.start+2*MINUTE)
        self.observations(5)
        self.observations(6, zero=["public_primary"])
        self.observations(7)
        self.run_archive()
        self.assertIsNone(self.events()[0][3])
        self.observations(8)
        self.run_archive()
        self.assertEqual(self.events()[0][3], self.start+7*MINUTE)

    def test_settlement_delay_accepts_late_missing_minute_before_evaluation(self):
        self.start = RUN-8*MINUTE
        self.observations(0, ["public_primary"])
        self.observations(2, ["public_primary"])
        self.run_archive()
        self.assertEqual(self.events(), [])
        self.observations(1, ["public_primary"])
        self.run_archive(NOW+timedelta(minutes=20))
        self.assertEqual(self.events()[0][1], self.start)

    def test_events_and_open_state_survive_raw_ttl_then_recover(self):
        for slot in range(3):
            self.observations(slot, ["public_primary", "public_control"])
        self.run_archive()
        before = self.events()
        future = NOW+timedelta(days=91)
        maintain(self.db, milliseconds(future), ROLES)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.events(), before)
        self.start = milliseconds(future)-30*MINUTE
        self.rows = []
        self.observations(0); self.observations(1)
        self.run_archive(future); self.run_archive(future)
        self.assertEqual(len(self.events()), 3)
        self.assertTrue(all(e[3] == self.start for e in self.events()))
        self.assertGreater(self.count("network_daily"), 6)

    def test_event_state_failure_rolls_back_incident_creation(self):
        self.db.execute("""CREATE TEMP TRIGGER fail_state BEFORE INSERT ON network_event_state
            BEGIN SELECT RAISE(ABORT,'synthetic'); END""")
        for slot in range(3):
            self.observations(slot, ["public_primary"])
        with self.assertRaises(sqlite3.Error):
            self.run_archive()
        self.assertEqual(self.count("network_events"), 0)
        self.db.execute("DROP TRIGGER fail_state")
        self.run_archive()
        self.assertEqual(self.count("network_events"), 1)

    def test_ambiguous_mapping_is_unknown(self):
        for slot in range(3):
            self.observations(slot, ["public_primary", "public_control"])
        self.monitors.append(monitor("duplicate-id", ROLE_TARGETS["upstream_gateway"]))
        self.assertEqual(self.run_archive()["network_correlation_ready"], 0)
        self.assertEqual(self.events("suspected_public_connectivity"), [])

    def test_disabled_lan_gateway_does_not_block_upstream_correlation(self):
        for slot in range(3):
            self.observations(slot, ["public_primary", "public_control"])
        self.monitors[0]["enabled"] = False
        self.assertEqual(self.run_archive()["network_correlation_ready"], 1)
        self.assertEqual(len(self.events("suspected_public_connectivity")), 1)

    def test_partial_api_round_defers_public_correlation_until_success(self):
        for slot in range(3):
            self.observations(slot, ["public_primary", "public_control"])
        api = API(self.rows, self.monitors)
        api.fail_on = 1
        report = collect(self.db, api, NOW, roles=ROLES)
        self.assertEqual(report["network_failed"], 1)
        self.assertEqual(self.events("suspected_public_connectivity"), [])
        self.run_archive()
        self.assertEqual(len(self.events("suspected_public_connectivity")), 1)

    def test_lan_metadata_change_does_not_restart_public_incident(self):
        for slot in range(3):
            self.observations(slot, ["public_primary", "public_control"])
        self.run_archive()
        self.monitors[0]["enabled"] = False
        self.run_archive()
        self.assertEqual(len(self.events("suspected_public_connectivity")), 1)

    def test_reused_monitor_id_rejects_rebinding_without_false_recovery(self):
        for slot in range(3):
            self.observations(slot, ["public_primary"])
        self.run_archive()
        original = self.events()[0]
        target = next(m for m in self.monitors if m["id"] == self.ids["public_primary"])
        target["target"] = "203.0.113.99"
        # Stop replaying the previous binding's samples in this synthetic API.
        self.rows = []
        self.observations(3); self.observations(4)
        report = self.run_archive()
        self.assertEqual(report["network_failed"], 1)
        self.assertIn(original, self.events())
        self.assertIsNone(self.events()[0][3])
        stored = self.db.execute("SELECT target FROM network_monitors WHERE monitor_id=?", (self.ids["public_primary"],)).fetchone()[0]
        self.assertEqual(stored, ROLE_TARGETS["public_primary"])


class MigrationTests(unittest.TestCase):
    def test_v1_v2_compatibility_atomic_additive_migration_and_reopen(self):
        for version in (1, 2):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                path = Path(temp)/"archive.sqlite3"
                with writer(path, lambda p: Path(p)) as db:
                    if version == 2:
                        migrate_frequency(db, 2, lambda: None)
                    db.execute("INSERT INTO checkpoints VALUES ('example','2026-11-11T00:00:00.000Z')")
                    db.execute("INSERT INTO samples VALUES ('example','record','2026-11-11T00:00:00.000Z','raw',NULL,'{}','archived')")
                    if version == 2:
                        db.execute("INSERT INTO cpu_frequency_samples VALUES ('device','sample','time','{}','received','archived')")
                    db.commit()
                    migrate(db, lambda: None); migrate(db, lambda: None)
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)
                    self.assertEqual(db.execute("SELECT count(*) FROM checkpoints").fetchone()[0], 1)
                    self.assertEqual(db.execute("SELECT count(*) FROM samples").fetchone()[0], 1)
                    self.assertEqual(db.execute("SELECT count(*) FROM cpu_frequency_samples").fetchone()[0], version-1)
                with writer(path, lambda p: Path(p)) as db:
                    self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertTrue(TABLES.keys() <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})

    def test_v1_v2_still_open_without_automatic_migration(self):
        for version in (1, 2):
            with tempfile.TemporaryDirectory() as temp:
                with writer(Path(temp)/"archive.sqlite3", lambda p: Path(p)) as db:
                    if version == 2:
                        migrate_frequency(db, 2, lambda: None)
                    with self.assertRaises(ArchiveError):
                        collect(db, API(), NOW)
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], version)

    def test_migration_mount_failure_rolls_back_all_new_tables_and_version(self):
        with tempfile.TemporaryDirectory() as temp:
            with writer(Path(temp)/"archive.sqlite3", lambda p: Path(p)) as db:
                with self.assertRaises(MountError):
                    migrate(db, Mock(side_effect=MountError("synthetic")))
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'network_%' OR name='cpu_frequency_samples'").fetchall(), [])

    def test_explicit_cli_backup_and_identical_rerun(self):
        spec = importlib.util.spec_from_file_location("network_migration_cli", ROOT/"tools/migrate_metrics_archive.py")
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as temp:
            path, backup = Path(temp)/"archive.sqlite3", Path(temp)/"before.sqlite3"
            with writer(path, lambda p: Path(p)) as db:
                db.execute("INSERT INTO checkpoints VALUES ('example','2026-11-11T00:00:00.000Z')"); db.commit()
            args = ["migrate", "--database", str(path), "--backup", str(backup), "--to", "3"]
            with patch.object(cli, "require_hdd", side_effect=lambda p, *a: Path(p)), patch("sys.argv", args):
                self.assertEqual(cli.main(), 0)
                snapshot = backup.read_bytes()
                self.assertEqual(cli.main(), 0)
                self.assertEqual(backup.read_bytes(), snapshot)
            with closing(sqlite3.connect(backup)) as db:
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT count(*) FROM checkpoints").fetchone()[0], 1)


class ClientConfigTests(unittest.TestCase):
    def test_api_only_get_numeric_cursor_and_opaque_string_escaping(self):
        client = BeszelClient("http://example.invalid")
        self.addCleanup(client.session.close)
        response = Mock(); response.json.return_value = {"items": []}
        with patch.object(client.session, "get", return_value=response) as get, patch.object(client.session, "post") as post:
            client.get_network_archive_page("abc1234", RUN-1000, RUN, (RUN-500, "0000000001"), 2)
            params = get.call_args.kwargs["params"]
            self.assertEqual((params["page"], params["sort"], params["perPage"]), (1, "created,id", 2))
            self.assertIn('monitor="abc1234"', params["filter"])
            self.assertIn("type='1m'", params["filter"])
            self.assertIn(f"created >= {RUN-1000}", params["filter"])
            self.assertIn('id > "0000000001"', params["filter"])
            client.get_network_archive_page('opaque"identity', 0, RUN)
            self.assertIn(json.dumps('opaque"identity'), get.call_args.kwargs["params"]["filter"])
            post.assert_not_called()
        with self.assertRaises(ValueError):
            client.get_network_archive_page(1234, 0, RUN)
        with self.assertRaises(ValueError):
            client.get_network_archive_page("abc12345", "ISO time", RUN)

    def test_private_role_file_validation_and_placeholder_example(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"roles.json"
            path.write_text(json.dumps(ROLES))
            self.assertEqual(load_roles(path), ROLES)
            self.assertIsNone(load_roles(""))
            for config in ({**ROLES, "abnormal_minutes": True},
                           {**ROLES, "recovery_minutes": 0},
                           {**ROLES, "targets": {**ROLE_TARGETS, "upstream_gateway": ROLE_TARGETS["lan_gateway"]}},
                           {**ROLES, "targets": {"public_primary": "<placeholder>"}}):
                path.write_text(json.dumps(config))
                with self.assertRaises((ValueError, KeyError)):
                    load_roles(path)
            with self.assertRaises(ValueError):
                load_roles(ROOT/"examples/network-archive-roles.json")


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portal-network-runner-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path, self.registry = self.root/"archive.sqlite3", self.root/"registry.db"
        self.guard = lambda p: Path(p)
        with writer(self.path, self.guard) as db:
            migrate(db, lambda: None)
        self.roles_path = self.root/"roles.json"
        self.roles_path.write_text(json.dumps(ROLES))
        spec = importlib.util.spec_from_file_location("network_archive_runner", ROOT/"tools/archive_metrics.py")
        self.runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.runner)
        self.config = SimpleNamespace(DATABASE_PATH=self.registry, BESZEL_URL="http://example.invalid",
            BESZEL_TIMEOUT=1, BESZEL_TOKEN="synthetic-secret", BESZEL_EMAIL="", BESZEL_PASSWORD="")
        self.api = API([sample()])
        self.api.session = Mock()
        self.api.authenticate_with_token = Mock()
        self.api.get_systems = Mock(return_value=[])

    def run_archive(self, now=NOW, **env):
        settings = {"METRICS_ARCHIVE_PATH": str(self.path), "NETWORK_ARCHIVE_ENABLED": "true",
                    "NETWORK_ARCHIVE_ROLES_FILE": str(self.roles_path), "FREQUENCY_ARCHIVE_ENABLED": "false", **env}
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", settings), patch.dict("sys.modules", {"config": self.config}), \
                patch.object(self.runner, "require_hdd", side_effect=lambda p, *a: Path(p)), \
                patch.object(self.runner, "BeszelClient", return_value=self.api), \
                patch("sys.stdout", output), patch("sys.stderr", errors):
            code = self.runner.main(now)
        text = output.getvalue()+errors.getvalue()
        self.assertNotIn("synthetic-secret", text)
        self.assertNotIn(ROLE_TARGETS["upstream_gateway"], text)
        return code, json.loads(output.getvalue())

    def test_shared_auth_frequency_drain_and_v3_history_readers(self):
        from frequency import receive, stamp
        from frequency_history import query as frequency_query
        from performance_history import query as performance_query
        with closing(sqlite3.connect(self.registry)) as db:
            db.executescript((ROOT/"schema.sql").read_text())
            db.execute("INSERT INTO devices(device_id) VALUES ('example-device')"); db.commit()
        receive(self.registry, "example-device", [dict(sample_id="a"*32, sampled_utc=stamp(NOW),
            cpu_frequency_ghz=1.4, source="linux_scaling_cur_freq", logical_cpu_count=4,
            valid_cpu_count=4, quality="ok", window_ms=0, error=None)], now=NOW)
        code, report = self.run_archive(FREQUENCY_ARCHIVE_ENABLED="true")
        self.assertEqual((code, report["frequency_archived"], report["network_inserted"]), (0, 1, 1))
        self.api.authenticate_with_token.assert_called_once_with("synthetic-secret")
        self.api.session.close.assert_called_once()
        with writer(self.path, self.guard) as db:
            start, end = stamp(NOW-timedelta(minutes=1)), stamp(NOW+timedelta(minutes=1))
            self.assertEqual(len(frequency_query(db, "example-device", start, end)["points"]), 1)
            result = performance_query(db, {"device_id": "example-device", "beszel_system_id": SYSTEM}, "hp", start, end, extended=True)
            self.assertEqual((result["status"], len(result["series"])), ("ok", 7))

    def test_auth_failure_keeps_local_retention_and_totals(self):
        with writer(self.path, self.guard) as db:
            collect(db, API([sample()]), NOW)
        self.api.authenticate_with_token.side_effect = APIConnectionError("synthetic-secret")
        code, report = self.run_archive(now=NOW+timedelta(days=91))
        self.assertEqual((code, report["network_failed"], report["network_pruned"]), (1, 1, 1))
        with writer(self.path, self.guard) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM network_samples").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT sample_count FROM network_daily").fetchone()[0], 1)

    def test_network_failure_reports_nonzero_without_failing_legacy_job(self):
        self.api.fail_on = 1
        code, report = self.run_archive()
        self.assertEqual((code, report["failed"], report["network_failed"]), (1, 0, 1))
        self.assertEqual(report["systems"], 0)

    def test_disabled_network_leaves_v1_archive_compatible(self):
        self.path = self.root/"legacy.sqlite3"
        with writer(self.path, self.guard):
            pass
        self.api.get_network_monitors_page = Mock(side_effect=AssertionError("must stay disabled"))
        code, report = self.run_archive(NETWORK_ARCHIVE_ENABLED="false")
        self.assertEqual((code, report["network_failed"]), (0, 0))
        with writer(self.path, self.guard) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
