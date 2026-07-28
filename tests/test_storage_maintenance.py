import gzip
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.storage_maintenance import (
    clear_regenerable_caches,
    compact_sqlite_database,
    create_consistent_sqlite_backup,
    gzip_file_chunks,
    run_storage_maintenance,
    sqlite_metrics,
)


class StorageMaintenanceTests(unittest.TestCase):
    def create_database(self, root: Path) -> Path:
        db_path = root / "db.db"
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                "CREATE TABLE articles ("
                "id TEXT PRIMARY KEY, content TEXT, content_html TEXT, has_content INTEGER)"
            )
            connection.execute("CREATE TABLE feeds (id TEXT PRIMARY KEY, name TEXT)")
            raw_page = "<html><script>" + ("x" * 2_000_000) + "</script></html>"
            cleaned = "<p>article body</p>"
            connection.execute(
                "INSERT INTO articles VALUES (?, ?, ?, ?)",
                ("legacy", raw_page, cleaned, 1),
            )
            connection.execute(
                "INSERT INTO articles VALUES (?, ?, ?, ?)",
                ("missing-clean", raw_page, None, 1),
            )
            connection.execute(
                "INSERT INTO articles VALUES (?, ?, ?, ?)",
                ("current", cleaned, cleaned, 1),
            )
            connection.execute("INSERT INTO feeds VALUES (?, ?)", ("feed", "Feed"))
            connection.commit()
        return db_path

    def test_compacts_legacy_content_without_changing_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.create_database(Path(temp_dir))
            before = db_path.stat().st_size

            result = compact_sqlite_database(
                db_path,
                cleaner=lambda _content: "<p>cleaned fallback</p>",
            )

            self.assertLess(db_path.stat().st_size, before)
            self.assertGreater(result["reclaimed_bytes"], 3_000_000)
            self.assertEqual(result["table_counts"], {"articles": 3, "feeds": 1})
            with sqlite3.connect(db_path) as connection:
                rows = connection.execute(
                    "SELECT id, content, content_html, has_content FROM articles ORDER BY id"
                ).fetchall()
                integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            self.assertEqual(integrity, "ok")
            self.assertEqual(rows[0][1:3], ("<p>article body</p>",) * 2)
            self.assertEqual(rows[1][1:3], ("<p>article body</p>",) * 2)
            self.assertEqual(rows[2][1:3], ("<p>cleaned fallback</p>",) * 2)

    def test_clears_only_regenerable_cache_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            for relative_path in ("cache/rss", "cache/content", "cache/views"):
                cache_dir = data_dir / relative_path
                cache_dir.mkdir(parents=True, exist_ok=True)
                (cache_dir / "entry").write_bytes(b"cache")
            (data_dir / "config.yaml").write_text("keep", encoding="utf-8")

            removed = clear_regenerable_caches(data_dir)

            self.assertEqual(sum(removed.values()), 15)
            self.assertFalse((data_dir / "cache/rss").exists())
            self.assertEqual((data_dir / "config.yaml").read_text(), "keep")

    def test_failed_replace_keeps_source_database_and_removes_compact_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self.create_database(Path(temp_dir))

            with (
                patch(
                    "tools.storage_maintenance.os.replace",
                    side_effect=OSError("stop"),
                ),
                self.assertRaisesRegex(OSError, "stop"),
            ):
                compact_sqlite_database(
                    db_path,
                    cleaner=lambda _content: "<p>cleaned fallback</p>",
                )

            self.assertTrue(db_path.exists())
            self.assertFalse(Path(f"{db_path}.compact").exists())
            with sqlite3.connect(db_path) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0], 3)

    def test_request_marker_makes_maintenance_one_shot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            db_path = self.create_database(data_dir)
            database_url = f"sqlite:///{db_path}"

            cleaner = lambda _content: "<p>cleaned fallback</p>"
            first = run_storage_maintenance(
                "test-v1", database_url, data_dir, cleaner=cleaner
            )
            second = run_storage_maintenance(
                "test-v1", database_url, data_dir, cleaner=cleaner
            )

            self.assertEqual(first["status"], "completed")
            self.assertEqual(second["status"], "skipped")
            self.assertTrue(sqlite_metrics(db_path)["exists"])

    def test_streamed_backup_is_consistent_and_removes_temporary_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            db_path = self.create_database(root)
            backup_path, metadata = create_consistent_sqlite_backup(db_path, root)

            compressed = b"".join(
                gzip_file_chunks(backup_path, remove_parent_on_close=True)
            )
            restored_path = root / "restored.db"
            restored_path.write_bytes(gzip.decompress(compressed))

            self.assertEqual(metadata["integrity"], "ok")
            self.assertFalse(backup_path.parent.exists())
            with sqlite3.connect(restored_path) as connection:
                self.assertEqual(
                    connection.execute("PRAGMA integrity_check").fetchone()[0],
                    "ok",
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
                    3,
                )


if __name__ == "__main__":
    unittest.main()
