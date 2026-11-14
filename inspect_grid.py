from pathlib import Path
import duckdb

path = Path('data/processed/punjab_1km_grid.parquet')

if not path.exists():
    print('ERROR: Grid file not found:', path)
    raise SystemExit(1)

with duckdb.connect() as db:
    print('\nGRID SCHEMA:')
    for name, dtype, *_ in db.execute(
        'DESCRIBE SELECT * FROM read_parquet(?)',
        [str(path)]
    ).fetchall():
        print(f'{name}: {dtype}')

    print('\nTOTAL GRID CELLS:')
    print(db.execute(
        'SELECT COUNT(*) FROM read_parquet(?)',
        [str(path)]
    ).fetchone()[0])

    print('\nFIRST 3 ROWS:')
    result = db.execute(
        'SELECT * FROM read_parquet(?) LIMIT 3',
        [str(path)]
    )
    columns = [col[0] for col in result.description]

    for row in result.fetchall():
        for name, value in zip(columns, row):
            text = str(value)
            print(f'{name}: {text[:250]}')
        print('---')
