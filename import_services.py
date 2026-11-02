#!/usr/bin/env python3
"""
One-shot import script: reads FREIA_network_devicesIP.csv and populates
device_service assignments from the EPICS and OS service columns.

Run once on the machine that has labnet.db:
    python3 import_services.py [path/to/labnet.db] [path/to/FREIA_network_devicesIP.csv]

Defaults:
    DB:  ./labnet.db
    CSV: ./FREIA_network_devicesIP.csv
"""
import csv
import io
import sqlite3
import sys
from pathlib import Path

DB_PATH  = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('labnet.db')
CSV_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('FREIA_network_devicesIP.csv')

# Column indices in the CSV (0-based, semicolon-delimited)
EPICS_COLS = list(range(9, 23))
OS_COLS    = list(range(24, 39))
HOST_COL   = 2   # 'Name' column

print(f'DB : {DB_PATH}')
print(f'CSV: {CSV_PATH}')

with open(CSV_PATH, encoding='utf-8-sig') as f:
    content = f.read()

reader = csv.reader(io.StringIO(content), delimiter=';')
rows   = list(reader)
if len(rows) < 2:
    sys.exit('CSV too short.')

col_headers = rows[1]

col_to_name = {}
for c in EPICS_COLS + OS_COLS:
    if c < len(col_headers):
        name = col_headers[c].strip()
        if name:
            col_to_name[c] = name

db = sqlite3.connect(str(DB_PATH))
db.row_factory = sqlite3.Row
db.execute('PRAGMA foreign_keys = ON')

svc_map = {r['name']: r['id'] for r in db.execute("SELECT id, name FROM service")}
if not svc_map:
    sys.exit('service table is empty — run the CREATE TABLE + INSERT SQL first.')

dev_map = {r['hostname']: r['id'] for r in db.execute("SELECT id, hostname FROM device")}

inserted = 0
skipped  = 0
no_host  = 0

for i, row in enumerate(rows[2:], start=3):
    hostname = row[HOST_COL].strip() if len(row) > HOST_COL else ''
    if not hostname:
        continue

    dev_id = dev_map.get(hostname)
    if dev_id is None:
        print(f'  [row {i}] SKIP — hostname not in DB: {hostname!r}')
        no_host += 1
        continue

    for c, svc_name in col_to_name.items():
        cell = row[c].strip() if len(row) > c else ''
        if not cell:
            continue
        svc_id = svc_map.get(svc_name)
        if svc_id is None:
            print(f'  [row {i}] WARN — service not in catalogue: {svc_name!r}')
            continue
        role = cell if cell.lower() not in ('yes',) else None
        try:
            db.execute(
                "INSERT OR IGNORE INTO device_service (device_id, service_id, role) VALUES (?,?,?)",
                (dev_id, svc_id, role))
            inserted += 1
        except sqlite3.IntegrityError:
            skipped += 1

db.commit()
db.close()

print(f'\nDone. {inserted} assignments imported, {skipped} already existed, '
      f'{no_host} hostnames not found in DB.')
