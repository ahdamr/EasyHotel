import csv
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "EasyHotel_Dataset_Large"
DB_PATH = BASE_DIR / "easyhotel.db"

if not DATA_DIR.exists():
    print("Error: Dataset folder was not found.")
    print("Please check the folder name.")
    raise SystemExit(1)

connection = sqlite3.connect(DB_PATH)
cursor = connection.cursor()

csv_files = list(DATA_DIR.glob("*.csv"))

if not csv_files:
    print("No CSV files were found.")
    connection.close()
    raise SystemExit(1)

for file_path in csv_files:
    table_name = file_path.stem

    with open(file_path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            print(f"Skipped empty file: {file_path.name}")
            continue

        columns = reader.fieldnames

        def quote_identifier(name):
            return '"' + name.replace('"', '""') + '"'

        column_definitions = ", ".join(
            f"{quote_identifier(column)} TEXT"
            for column in columns
        )

        cursor.execute(
            f"CREATE TABLE IF NOT EXISTS "
            f"{quote_identifier(table_name)} "
            f"({column_definitions})"
        )

        cursor.execute(
            f"DELETE FROM {quote_identifier(table_name)}"
        )

        placeholders = ", ".join(["?"] * len(columns))
        column_names = ", ".join(
            quote_identifier(column) for column in columns
        )

        insert_query = (
            f"INSERT INTO {quote_identifier(table_name)} "
            f"({column_names}) VALUES ({placeholders})"
        )

        rows = [
            tuple(row.get(column, "") or "" for column in columns)
            for row in reader
        ]

        cursor.executemany(insert_query, rows)

        print(f"{table_name}: imported {len(rows)} records")

connection.commit()
connection.close()

print("\nDatabase created successfully!")
print(f"Location: {DB_PATH}")