"""Archive recovery and mount contracts; temporary databases only / 仅临时库。"""
from datetime import datetime, timedelta, timezone
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from beszel_client import BeszelClient
from metrics_archive import ArchiveError, MountError, collect, require_hdd, stamp, utc_time, writer

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
SYSTEM = "a" * 15
OTHER = "b" * 15
TEST_UUID = "00000000-0000-0000-0000-000000000001"  # synthetic / 合成值


def sample(index, when=None, system=SYSTEM):
    return {"id": f"{index:015d}", "system": system, "type": "1m",
            "created": stamp(when or NOW - timedelta(minutes=20-index)).replace("T", " "),
            "updated": stamp(NOW), "stats": {"cpu": 0, "mp": None, "efs": {"hdd": {"du": 16}},
                                            "future_metric": [1, 2]}}


class FakeClient:
    def __init__(self, records, systems=None):
        self.records = records
        self.systems = systems or [SYSTEM]
        self.calls = []
        self.fail_on = None

    def get_systems(self):
        return [{"id": s} for s in self.systems]

    def get_archive_page(self, system, start, end, after, per_page):
        self.calls.append((system, start, end, after, per_page))
        if self.fail_on == len(self.calls):
            raise RuntimeError("private upstream error")
        rows = sorted((r for r in self.records if r["system"] == system
                       and utc_time(start) <= utc_time(r["created"]) <= utc_time(end)),
                      key=lambda r: (r["created"], r["id"]))
        if after:
            rows = [r for r in rows if (r["created"], r["id"]) > after]
        return rows[:per_page]


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="portal-archive-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "archive" / "metrics.sqlite3"
        # Injected only in tests; command-line runner has no bypass option.
        self.guard = lambda path: Path(path)
        self.ctx = writer(self.path, self.guard)
        self.db = self.ctx.__enter__()
        self.addCleanup(self.ctx.__exit__, None, None, None)

    def count(self):
        return self.db.execute("SELECT count(*) FROM samples").fetchone()[0]

    def test_pagination_dedup_raw_and_utc(self):
        client = FakeClient([sample(i) for i in range(1, 8)])
        report = collect(self.db, client, NOW, page_size=2)
        self.assertEqual(report["inserted"], 7)
        self.assertEqual(len(client.calls), 5)
        self.assertEqual(collect(self.db, client, NOW, page_size=2)["inserted"], 0)
        self.assertEqual(self.count(), 7)
        row = self.db.execute("SELECT created_utc,created_raw,stats_json FROM samples LIMIT 1").fetchone()
        self.assertIn("T", row[0]); self.assertIn(" ", row[1])
        self.assertEqual(json.loads(row[2])["future_metric"], [1, 2])
        self.assertEqual(json.loads(row[2])["cpu"], 0)
        self.assertIsNone(json.loads(row[2])["mp"])

    def test_interruption_commits_page_and_recovers(self):
        client = FakeClient([sample(i) for i in range(1, 8)])
        client.fail_on = 2
        self.assertEqual(collect(self.db, client, NOW, page_size=2)["failed"], 1)
        self.assertEqual(self.count(), 2)
        self.assertEqual(self.db.execute("SELECT created_utc FROM checkpoints").fetchone()[0],
                         stamp(utc_time(sample(2)["created"])))
        client.fail_on = None
        self.assertEqual(collect(self.db, client, NOW, page_size=2)["inserted"], 5)
        self.assertEqual(self.count(), 7)

    def test_same_timestamp_cursor_and_late_sample(self):
        when = NOW - timedelta(minutes=2)
        client = FakeClient([sample(i, when) for i in range(1, 6)])
        collect(self.db, client, NOW, page_size=2)
        client.records.append(sample(6, when - timedelta(minutes=3)))
        self.assertEqual(collect(self.db, client, NOW, page_size=2)["inserted"], 1)
        self.assertEqual(self.count(), 6)

    def test_failed_device_does_not_block_other_devices(self):
        client = FakeClient([sample(1, system=OTHER)], [SYSTEM, OTHER])
        client.fail_on = 1
        report = collect(self.db, client, NOW)
        self.assertEqual((report["failed"], report["inserted"]), (1, 1))
        self.assertEqual(self.db.execute("SELECT system_id FROM checkpoints").fetchall(), [(OTHER,)])

    def test_empty_device_does_not_advance(self):
        collect(self.db, FakeClient([]), NOW)
        self.assertEqual(self.db.execute("SELECT count(*) FROM checkpoints").fetchone()[0], 0)

    def test_retention_boundary(self):
        boundary = NOW - timedelta(days=180)
        collect(self.db, FakeClient([sample(1, boundary), sample(2, boundary + timedelta(seconds=1))]), NOW)
        self.assertEqual(self.count(), 2)
        report = collect(self.db, FakeClient([]), NOW + timedelta(milliseconds=1))
        self.assertEqual(report["pruned"], 1)
        self.assertEqual(self.count(), 1)

    def test_invalid_page_rolls_back_without_checkpoint(self):
        bad = sample(2); bad["stats"] = {"cpu": float("nan")}
        client = Mock()
        client.get_systems.return_value = [{"id": SYSTEM}]
        client.get_archive_page.return_value = [sample(1), bad]
        self.assertEqual(collect(self.db, client, NOW)["failed"], 1)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM checkpoints").fetchone()[0], 0)

    def test_network_failure_isolated(self):
        from requests.exceptions import Timeout
        client = Mock()
        client.get_systems.return_value = [{"id": SYSTEM}]
        client.get_archive_page.side_effect = Timeout("sensitive response")
        self.assertEqual(collect(self.db, client, NOW)["failed"], 1)
        self.assertEqual(self.count(), 0)

    def test_writer_lock(self):
        with self.assertRaises(ArchiveError):
            with writer(self.path, self.guard):
                pass

    def test_existing_portal_database_is_rejected(self):
        path = Path(self.temp.name) / "portal.sqlite3"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE devices (device_id TEXT)")
        with self.assertRaises(ArchiveError):
            with writer(path, self.guard):
                pass
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                             [("devices",)])

    def test_mount_loss_blocks_page_commit(self):
        check = Mock(side_effect=MountError("HDD unavailable"))
        with self.assertRaises(ArchiveError):
            collect(self.db, FakeClient([sample(1)]), NOW, check_mount=check)
        self.assertEqual(self.count(), 0)
        self.assertEqual(check.call_count, 1)

    def test_repeated_page_is_rejected(self):
        client = Mock()
        client.get_systems.return_value = [{"id": SYSTEM}]
        client.get_archive_page.return_value = [sample(1)]
        report = collect(self.db, client, NOW)
        self.assertEqual((report["inserted"], report["failed"]), (1, 1))
        self.assertEqual(client.get_archive_page.call_count, 2)

    def test_ten_devices_and_bounded_page_memory(self):
        systems = [f"{i:015d}" for i in range(10)]
        rows = [sample(i, NOW - timedelta(minutes=100-i), s) for s in systems for i in range(30)]
        client = FakeClient(rows, systems)
        report = collect(self.db, client, NOW, page_size=7)
        self.assertEqual((report["systems"], report["inserted"], report["failed"]), (10, 300, 0))
        self.assertTrue(all(call[-1] == 7 for call in client.calls))

    def test_checkpoint_write_failure_rolls_back_entire_page(self):
        self.db.execute("""CREATE TEMP TRIGGER fail_checkpoint BEFORE INSERT ON checkpoints
                          BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        report = collect(self.db, FakeClient([sample(1), sample(2)]), NOW)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["inserted"], 0)
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.db.execute("SELECT count(*) FROM checkpoints").fetchone()[0], 0)
        self.db.execute("DROP TRIGGER fail_checkpoint")
        self.assertEqual(collect(self.db, FakeClient([sample(1), sample(2)]), NOW)["inserted"], 2)

    def test_future_and_submillisecond_records_rejected(self):
        for created in (stamp(NOW + timedelta(seconds=1)), "2026-10-12T19:59:59.123456Z"):
            record = sample(1); record["created"] = created
            client = Mock()
            client.get_systems.return_value = [{"id": SYSTEM}]
            client.get_archive_page.return_value = [record]
            self.assertEqual(collect(self.db, client, NOW)["failed"], 1)
            self.assertEqual(self.count(), 0)

    def test_wal_online_backup_restore_content_and_checkpoint(self):
        self.db.execute("PRAGMA wal_autocheckpoint=0")
        records = [sample(i, system=s) for s in (SYSTEM, OTHER) for i in range(1, 9)]
        self.assertEqual(collect(self.db, FakeClient(records, [SYSTEM, OTHER]), NOW, page_size=3)["inserted"], 16)
        self.assertGreater(Path(str(self.path) + "-wal").stat().st_size, 0)
        backup = Path(self.temp.name) / "backup.sqlite3"
        restored = Path(self.temp.name) / "restored.sqlite3"
        def contents(db):
            return (db.execute("SELECT * FROM samples ORDER BY system_id,record_id").fetchall(),
                    db.execute("SELECT * FROM checkpoints ORDER BY system_id").fetchall())
        expected = contents(self.db)
        backup.touch(mode=0o600)
        restored.touch(mode=0o600)
        with closing(sqlite3.connect(backup)) as destination:
            self.db.backup(destination)
            self.assertEqual(destination.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(contents(destination), expected)
            with closing(sqlite3.connect(restored)) as recovery:
                destination.backup(recovery)
                self.assertEqual(recovery.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(contents(recovery), expected)
        restored.chmod(0o600)
        with writer(restored, self.guard) as recovery:
            report = collect(recovery, FakeClient(records, [SYSTEM, OTHER]), NOW, page_size=3)
            self.assertEqual(report["inserted"], 0)
            self.assertEqual(contents(recovery), expected)


class MountTests(unittest.TestCase):
    def test_wrong_uuid_missing_mount_readonly_and_nested_mount(self):
        with tempfile.TemporaryDirectory(prefix="portal-mount-") as temp:
            root = Path(temp); dest = root / "new" / "archive.sqlite3"
            valid = {"target": str(root), "uuid": TEST_UUID, "fstype": "ext4", "options": "rw,relatime"}
            for changes in ({"uuid": "ssd-uuid"}, {"target": "/"}, {"options": "ro"},
                            {"target": str(root / "nested")}):
                entry = {**valid, **changes}
                result = Mock(stdout=json.dumps({"filesystems": [entry]}))
                with patch("metrics_archive.subprocess.run", return_value=result):
                    with self.assertRaises(ArchiveError):
                        with writer(dest, lambda p: require_hdd(p, root, TEST_UUID)):
                            pass
                self.assertFalse(dest.parent.exists())
            with patch("metrics_archive.subprocess.run", return_value=Mock(stdout=json.dumps({"filesystems": [valid]}))):
                self.assertEqual(require_hdd(dest, root, TEST_UUID), dest)

    def test_symlink_escape_and_outside_path(self):
        with tempfile.TemporaryDirectory(prefix="portal-mount-") as temp:
            root = Path(temp) / "hdd"; root.mkdir()
            (root / "escape").symlink_to(Path(temp), target_is_directory=True)
            for path in (Path(temp) / "db", root / "escape" / "db"):
                with self.assertRaises(ArchiveError):
                    require_hdd(path, root, TEST_UUID)

    def test_missing_uuid_fails_before_directory_or_sqlite(self):
        with tempfile.TemporaryDirectory(prefix="portal-mount-") as temp:
            path = Path(temp) / "missing" / "archive.sqlite3"
            with patch("metrics_archive.sqlite3.connect") as connect:
                with self.assertRaises(MountError):
                    with writer(path):
                        pass
                connect.assert_not_called()
            self.assertFalse(path.parent.exists())

    def test_links_for_database_lock_and_sidecars_rejected(self):
        with tempfile.TemporaryDirectory(prefix="portal-mount-") as temp:
            root = Path(temp); database = root / "metrics.sqlite3"
            unrelated = root / "unrelated"; unrelated.write_bytes(b"unchanged")
            unrelated.chmod(0o600)
            for suffix in ("", ".lock", "-wal", "-shm", "-journal"):
                linked = Path(str(database) + suffix)
                for kind in ("symlink", "hardlink"):
                    if kind == "symlink":
                        linked.symlink_to(unrelated)
                    else:
                        linked.hardlink_to(unrelated)
                    with patch("metrics_archive.sqlite3.connect") as connect:
                        with self.assertRaises(MountError):
                            with writer(database, lambda p: Path(p)):
                                pass
                        connect.assert_not_called()
                    self.assertEqual(unrelated.read_bytes(), b"unchanged")
                    linked.unlink()

    def test_world_writable_parent_rejected(self):
        with tempfile.TemporaryDirectory(prefix="portal-mount-") as temp:
            unsafe = Path(temp) / "unsafe"; unsafe.mkdir(); unsafe.chmod(0o777)
            with self.assertRaises(MountError):
                with writer(unsafe / "archive.sqlite3", lambda p: Path(p)):
                    pass

    def test_missing_findmnt_and_invalid_json_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="portal-mount-") as temp:
            for failure in (FileNotFoundError(), None):
                with patch("metrics_archive.subprocess.run", side_effect=failure,
                           return_value=Mock(stdout="invalid JSON")):
                    with self.assertRaises(MountError):
                        require_hdd(Path(temp) / "db", Path(temp), TEST_UUID)

    def test_utc_rejects_naive_and_normalizes_offset(self):
        with self.assertRaises(ArchiveError):
            utc_time("2026-10-12 20:00:00")
        self.assertEqual(stamp(utc_time("2026-10-12T16:00:00-04:00")), stamp(NOW))


class ClientTests(unittest.TestCase):
    def test_cursor_filter_and_projection(self):
        client = BeszelClient("http://example.invalid")
        response = Mock(); response.json.return_value = {"items": []}
        with patch.object(client.session, "get", return_value=response) as get:
            client.get_archive_page(SYSTEM, "2026-10-12 19:00:00.000Z", "2026-10-12 20:00:00.000Z",
                                    ("2026-10-12 19:30:00.000Z", "1" * 15))
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["sort"], "created,id")
        self.assertIn("id > '111111111111111'", params["filter"])
        self.assertIn("stats", params["fields"])


if __name__ == "__main__":
    unittest.main()
