from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zlib
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path


def resolve_sqlite_path(database_url: str, cwd: Path | None = None) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix) or database_url == "sqlite:///:memory:":
        raise ValueError("storage maintenance requires a file-backed SQLite database")

    path = Path(database_url[len(prefix):]).expanduser()
    if not path.is_absolute():
        path = (cwd or Path.cwd()) / path
    return path.resolve()


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size

    total = 0
    for root, directories, files in os.walk(path, followlinks=False):
        directories[:] = [
            name for name in directories if not (Path(root) / name).is_symlink()
        ]
        for name in files:
            file_path = Path(root) / name
            try:
                if not file_path.is_symlink():
                    total += file_path.stat().st_size
            except FileNotFoundError:
                continue
    return total


def sqlite_metrics(db_path: Path) -> dict:
    if not db_path.exists():
        return {"exists": False, "path": str(db_path)}

    with closing(
        sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    ) as connection:
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        freelist_count = int(
            connection.execute("PRAGMA freelist_count").fetchone()[0]
        )
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])

    return {
        "exists": True,
        "path": str(db_path),
        "file_bytes": db_path.stat().st_size,
        "page_size": page_size,
        "page_count": page_count,
        "freelist_count": freelist_count,
        "reclaimable_bytes": freelist_count * page_size,
        "journal_mode": journal_mode,
        "wal_bytes": Path(f"{db_path}-wal").stat().st_size
        if Path(f"{db_path}-wal").exists()
        else 0,
    }


def storage_report(data_dir: Path, db_path: Path) -> dict:
    entries = {}
    if data_dir.exists():
        for entry in sorted(data_dir.iterdir(), key=lambda item: item.name):
            entries[entry.name] = directory_size(entry)

    usage = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.parent)
    return {
        "path": str(data_dir),
        "total_bytes": directory_size(data_dir),
        "filesystem": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
        "entries": entries,
        "sqlite": sqlite_metrics(db_path),
    }


def _table_row_counts(connection: sqlite3.Connection) -> dict[str, int]:
    table_names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    counts = {}
    for table_name in table_names:
        quoted_name = table_name.replace('"', '""')
        counts[table_name] = int(
            connection.execute(f'SELECT COUNT(*) FROM "{quoted_name}"').fetchone()[0]
        )
    return counts


def create_consistent_sqlite_backup(
    db_path: Path,
    temp_root: Path | None = None,
) -> tuple[Path, dict]:
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    backup_dir = Path(
        tempfile.mkdtemp(
            prefix="werss-sqlite-backup-",
            dir=str(temp_root) if temp_root else None,
        )
    )
    backup_path = backup_dir / "db.sqlite"
    try:
        with (
            closing(
                sqlite3.connect(
                    f"file:{db_path}?mode=ro",
                    uri=True,
                    timeout=60,
                )
            ) as source,
            closing(sqlite3.connect(backup_path)) as destination,
        ):
            source.execute("PRAGMA busy_timeout=60000")
            source.backup(destination, pages=1024, sleep=0.05)

        with closing(sqlite3.connect(backup_path)) as backup_connection:
            integrity = backup_connection.execute("PRAGMA integrity_check").fetchone()[0]
            table_counts = _table_row_counts(backup_connection)
        if integrity != "ok":
            raise RuntimeError(f"backup integrity check failed: {integrity}")

        return backup_path, {
            "integrity": integrity,
            "file_bytes": backup_path.stat().st_size,
            "table_counts": table_counts,
        }
    except Exception:
        shutil.rmtree(backup_dir, ignore_errors=True)
        raise


def gzip_file_chunks(
    source_path: Path,
    chunk_size: int = 1024 * 1024,
    remove_parent_on_close: bool = False,
) -> Iterator[bytes]:
    compressor = zlib.compressobj(level=6, method=zlib.DEFLATED, wbits=31)
    try:
        with source_path.open("rb") as source:
            while chunk := source.read(chunk_size):
                compressed = compressor.compress(chunk)
                if compressed:
                    yield compressed
            tail = compressor.flush()
            if tail:
                yield tail
    finally:
        if remove_parent_on_close:
            shutil.rmtree(source_path.parent, ignore_errors=True)


def _default_cleaner(content: str) -> str:
    from core.article_content import clean_article_content

    return clean_article_content(content)


def migrate_legacy_article_content(
    connection: sqlite3.Connection,
    cleaner: Callable[[str], str] = _default_cleaner,
    batch_size: int = 20,
) -> dict:
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'articles'"
    ).fetchone()
    if not table_exists:
        return {"scanned": 0, "updated": 0, "bytes_before": 0, "bytes_after": 0}

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(articles)").fetchall()
    }
    required_columns = {"id", "content", "content_html", "has_content"}
    if not required_columns.issubset(columns):
        raise RuntimeError("articles table is missing content migration columns")

    scanned = 0
    updated = 0
    bytes_before = 0
    bytes_after = 0
    cursor = connection.execute(
        "SELECT id, content, content_html FROM articles "
        "WHERE content IS NOT NULL OR content_html IS NOT NULL"
    )

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break

        for article_id, content, content_html in rows:
            content = (content or "").strip()
            content_html = (content_html or "").strip()
            scanned += 1
            bytes_before += len(content.encode("utf-8")) + len(
                content_html.encode("utf-8")
            )

            if content_html and content_html != content:
                cleaned = content_html
            elif content and (
                not content_html
                or len(content) > 256 * 1024
                or "<html" in content[:65536].lower()
                or "<script" in content[:65536].lower()
            ):
                cleaned = (cleaner(content) or "").strip()
            else:
                cleaned = content_html or content

            bytes_after += len(cleaned.encode("utf-8")) * 2
            if cleaned == content and cleaned == content_html:
                continue

            connection.execute(
                "UPDATE articles SET content = ?, content_html = ?, has_content = ? "
                "WHERE id = ?",
                (cleaned or None, cleaned or None, 1 if cleaned else 0, article_id),
            )
            updated += 1

        connection.commit()

    return {
        "scanned": scanned,
        "updated": updated,
        "bytes_before": bytes_before,
        "bytes_after": bytes_after,
    }


def clear_regenerable_caches(data_dir: Path) -> dict:
    removed = {}
    for relative_path in ("cache/rss", "cache/content", "cache/views"):
        cache_path = data_dir / relative_path
        removed[relative_path] = directory_size(cache_path)
        if cache_path.exists():
            shutil.rmtree(cache_path)
    return removed


def compact_sqlite_database(
    db_path: Path,
    cleaner: Callable[[str], str] = _default_cleaner,
    low_space: bool = False,
    temp_dir: Path | None = None,
) -> dict:
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    if low_space:
        compact_dir = temp_dir or Path(tempfile.gettempdir())
        compact_dir.mkdir(parents=True, exist_ok=True)
        descriptor, compact_name = tempfile.mkstemp(
            prefix=f"{db_path.name}.", suffix=".compact", dir=compact_dir
        )
        os.close(descriptor)
        compact_path = Path(compact_name)
    else:
        compact_path = db_path.with_name(f"{db_path.name}.compact")
    compact_path.unlink(missing_ok=True)
    original_mode = stat.S_IMODE(db_path.stat().st_mode)
    try:
        with closing(sqlite3.connect(db_path, timeout=60)) as connection:
            connection.execute("PRAGMA busy_timeout=60000")
            connection.execute(
                "PRAGMA journal_mode=OFF" if low_space else "PRAGMA journal_mode=DELETE"
            )
            migration = migrate_legacy_article_content(connection, cleaner=cleaner)
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            expected_counts = _table_row_counts(connection)
            escaped_path = str(compact_path).replace("'", "''")
            connection.execute(f"VACUUM INTO '{escaped_path}'")

        with closing(sqlite3.connect(compact_path)) as compact_connection:
            integrity = compact_connection.execute("PRAGMA integrity_check").fetchone()[0]
            compact_counts = _table_row_counts(compact_connection)
        if integrity != "ok":
            raise RuntimeError(f"compacted database integrity check failed: {integrity}")
        if compact_counts != expected_counts:
            raise RuntimeError("compacted database row counts do not match the source")

        original_bytes = db_path.stat().st_size
        compact_bytes = compact_path.stat().st_size
        os.chmod(compact_path, original_mode)
        if low_space:
            with compact_path.open("rb") as source, db_path.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            os.chmod(db_path, original_mode)
            replacement_mode = "verified_non_atomic_copy"
        else:
            os.replace(compact_path, db_path)
            replacement_mode = "atomic_replace"
        for suffix in ("-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)

        with closing(sqlite3.connect(db_path)) as replacement_connection:
            replacement_integrity = replacement_connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]
        if replacement_integrity != "ok":
            raise RuntimeError(
                f"replacement database integrity check failed: {replacement_integrity}"
            )

        return {
            "migration": migration,
            "original_bytes": original_bytes,
            "compacted_bytes": compact_bytes,
            "reclaimed_bytes": max(0, original_bytes - compact_bytes),
            "table_counts": expected_counts,
            "replacement_mode": replacement_mode,
        }
    finally:
        compact_path.unlink(missing_ok=True)


def run_storage_maintenance(
    request_id: str,
    database_url: str,
    data_dir: Path,
    cleaner: Callable[[str], str] = _default_cleaner,
    low_space: bool = False,
    temp_dir: Path | None = None,
) -> dict:
    normalized_id = re.sub(r"[^A-Za-z0-9_.-]", "_", request_id.strip())
    if not normalized_id:
        raise ValueError("storage maintenance request id is empty")

    data_dir = data_dir.resolve()
    db_path = resolve_sqlite_path(database_url)
    data_dir.mkdir(parents=True, exist_ok=True)
    marker = data_dir / f".storage-maintenance-{normalized_id}.done"
    if marker.exists():
        result = {"status": "skipped", "reason": "already_completed", "marker": str(marker)}
        print(f"storage_maintenance={json.dumps(result, ensure_ascii=True)}", flush=True)
        return result

    before = storage_report(data_dir, db_path)
    caches = clear_regenerable_caches(data_dir)
    compact = compact_sqlite_database(
        db_path,
        cleaner=cleaner,
        low_space=low_space,
        temp_dir=temp_dir,
    )
    after = storage_report(data_dir, db_path)
    result = {
        "status": "completed",
        "request_id": normalized_id,
        "before": before,
        "caches_removed": caches,
        "compact": compact,
        "after": after,
    }
    marker.write_text(json.dumps(result, ensure_ascii=True), encoding="utf-8")
    print(f"storage_maintenance={json.dumps(result, ensure_ascii=True)}", flush=True)
    return result


def main() -> None:
    request_id = os.getenv("WERSS_COMPACT_STORAGE_ON_START", "").strip()
    if not request_id:
        return

    database_url = os.getenv("DB", "sqlite:///./data/db.db")
    data_dir = Path(os.getenv("WERSS_DATA_DIR", "./data"))
    low_space = os.getenv("WERSS_STORAGE_LOW_SPACE_MODE", "").lower() == "true"
    backup_verified = os.getenv(
        "WERSS_STORAGE_EXTERNAL_BACKUP_VERIFIED", ""
    ).lower() == "true"
    if low_space and not backup_verified:
        raise RuntimeError(
            "low-space storage maintenance requires a verified external backup"
        )
    run_storage_maintenance(
        request_id,
        database_url,
        data_dir,
        low_space=low_space,
    )


if __name__ == "__main__":
    main()
