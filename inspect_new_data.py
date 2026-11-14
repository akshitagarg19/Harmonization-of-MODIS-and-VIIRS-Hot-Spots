from pathlib import Path
import duckdb

DATA_DIR = Path("data/processed")

files = [
    "monthly_aoi_anomalies.parquet",
    "weekly_aoi_anomalies.parquet",
    "monthly_harmonized.parquet",
    "weekly_harmonized.parquet",
]

with duckdb.connect() as db:
    for filename in files:
        path = DATA_DIR / filename

        print(f"\n{'=' * 60}")
        print(f"FILE: {filename}")

        if not path.exists():
            print("ERROR: File not found")
            continue

        schema = db.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)",
            [str(path)]
        ).fetchall()

        print("\nCOLUMNS:")
        for column in schema:
            print(f"  {column[0]}: {column[1]}")

        count = db.execute(
            "SELECT COUNT(*) FROM read_parquet(?)",
            [str(path)]
        ).fetchone()[0]

        print(f"\nTOTAL RECORDS: {count}")

        sample = db.execute(
            "SELECT * FROM read_parquet(?) LIMIT 2",
            [str(path)]
        )

        names = [column[0] for column in sample.description]
        for record in sample.fetchall():
            print(dict(zip(names, record)))

print("\nInspection complete.")
