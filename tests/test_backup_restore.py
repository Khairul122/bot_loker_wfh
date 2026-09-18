import sqlite3
import shutil
import unittest
from contextlib import closing
from pathlib import Path

from bot_loker_wfh.backup import backup_database, restore_database
from bot_loker_wfh.database import apply_schema


class BackupRestoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_path = Path("tmp") / "backup_restore_tests"
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)
        self.temp_path.mkdir(parents=True)

    def tearDown(self):
        if self.temp_path.exists():
            shutil.rmtree(self.temp_path)

    def test_backup_then_restore_to_empty_database(self):
        source = self.temp_path / "source.db"
        backup = self.temp_path / "backup.sqlite"
        restored = self.temp_path / "restored.db"
        with closing(sqlite3.connect(source)) as connection:
            apply_schema(connection)
            connection.execute(
                "INSERT INTO jobs (id, source, external_id, source_external_key, "
                "canonical_fingerprint, title, company, description, apply_url) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("job-1", "remoteok", "1", "remoteok:1", "fp-1", "Backend", "Acme", "desc", "https://example.com/job"),
            )
            connection.commit()

        backup_database(source, backup)
        restore_database(backup, restored)

        with closing(sqlite3.connect(restored)) as connection:
            self.assertEqual(
                connection.execute("SELECT title FROM jobs WHERE id = 'job-1'").fetchone()[0],
                "Backend",
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM filters").fetchone()[0],
                1,
            )

    def test_backup_is_sqlite_file_not_env_archive(self):
        source = self.temp_path / "source.db"
        backup = self.temp_path / "backup.sqlite"
        (self.temp_path / ".env").write_text("SECRET=do-not-copy", encoding="utf-8")
        with closing(sqlite3.connect(source)) as connection:
            apply_schema(connection)

        backup_database(source, backup)

        self.assertTrue(backup.exists())
        self.assertNotIn("do-not-copy", backup.read_bytes().decode("latin1", errors="ignore"))


if __name__ == "__main__":
    unittest.main()
