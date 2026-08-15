import argparse
import sqlite3
from pathlib import Path


def _count(connection: sqlite3.Connection, table: str) -> int:
    return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create and verify a MissionOps SQLite backup")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit(f"source database does not exist: {args.source}")
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    if args.destination.exists():
        args.destination.unlink()

    with sqlite3.connect(f"file:{args.source}?mode=ro", uri=True) as source:
        with sqlite3.connect(args.destination) as destination:
            source.backup(destination)

    with sqlite3.connect(f"file:{args.destination}?mode=ro", uri=True) as backup:
        integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
        passes = _count(backup, "pass")
        observations = _count(backup, "observation")

    print(f"integrity_check={integrity}")
    print(f"passes={passes}")
    print(f"observations={observations}")
    return 0 if integrity == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())