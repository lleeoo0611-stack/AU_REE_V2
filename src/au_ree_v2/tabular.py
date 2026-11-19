"""CSV interchange for the evidence, research and release layers."""
import csv
from pathlib import Path


def read_csv(path):
    path = Path(path)
    if not path.is_file():
        return []
    limit = csv.field_size_limit()
    try:
        csv.field_size_limit(max(limit, 16 * 1024 * 1024))
        with path.open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))
    finally:
        csv.field_size_limit(limit)


def write_csv(path, rows, columns):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
