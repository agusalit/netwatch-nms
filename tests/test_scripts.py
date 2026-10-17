import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import register_testbed  # noqa: E402
import reset_database  # noqa: E402


def test_backup_is_a_consistent_copy_and_row_counts_work(tmp_path):
    db_file = tmp_path / "netwatch.db"
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE devices (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO devices DEFAULT VALUES")
        conn.execute("INSERT INTO devices DEFAULT VALUES")
    assert reset_database.row_counts(db_file) == {"devices": 2, "status_logs": 0, "traffic_logs": 0}

    copy = reset_database.backup(db_file)
    assert copy.parent == tmp_path / "backups"
    assert reset_database.row_counts(copy)["devices"] == 2


def test_testbed_registration_prefers_eth0():
    descr = {1: "lo", 2: "tunl0", 7: "eth0"}
    assert register_testbed.pick_data_interface(descr, {1: "1", 7: "1"}, {}) == 7


def test_testbed_registration_falls_back_to_first_up_non_loopback():
    descr = {1: "lo", 3: "ens4", 5: "ens5"}
    assert register_testbed.pick_data_interface(descr, {1: "1", 3: "2", 5: "1"}, {}) == 5
    assert register_testbed.pick_data_interface({1: "lo"}, {1: "1"}, {}) is None
