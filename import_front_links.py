#!/usr/bin/env python3
"""
import_front_links.py
Run locally: python3 import_front_links.py labnet.db

Adds front-port links (patch panel → switch) based on:
  - POL90-30008-FREIA.csv  (main distribution switch, room 30008)
  - Contacts_part1.csv     (sw-loc-1 connections for 21D and 31A panels)

Also:
  - Creates POL90-30008-FREIA switch device (48 ports)
  - Creates sw-loc-elLab switch device (8 ports, unmanaged D-Link in elec. lab)
  - Creates outlet-30000 (FREIA bunker, ports 1-2)
  - Extends patch-panel-31A to 24 ports (adds 13-24)
  - Extends patch-panel-11D to 24 ports (adds 02-24)
  - Fixes 31A:12 back-link: outlet-30101:5 → outlet-30101:6
  - Adds known back-port links for newly discovered 11D connections
"""
import sqlite3, sys, os

DB = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~') + '/mnt/cables/labnet_web/labnet.db'
con = sqlite3.connect(DB)
cur = con.cursor()

stats = dict(devices=0, ifaces=0, links=0, fixes=0)

# ── helpers ────────────────────────────────────────────────────────────────

def get_device_id(hostname):
    r = cur.execute("SELECT id FROM device WHERE hostname=?", (hostname,)).fetchone()
    return r[0] if r else None

def ensure_device(hostname, kind, description=''):
    did = get_device_id(hostname)
    if did is None:
        cur.execute("INSERT INTO device (hostname, kind, notes) VALUES (?,?,?)",
                    (hostname, kind, description))
        did = cur.lastrowid
        stats['devices'] += 1
        print(f"  + device  {hostname} ({kind})")
    return did

def get_iface_id(device_hostname, name):
    r = cur.execute("""
        SELECT i.id FROM iface i
        JOIN device d ON d.id=i.device_id
        WHERE d.hostname=? AND i.name=?
    """, (device_hostname, name)).fetchone()
    return r[0] if r else None

def ensure_iface(device_hostname, name, kind='port'):
    iid = get_iface_id(device_hostname, name)
    if iid is None:
        did = get_device_id(device_hostname)
        cur.execute("INSERT INTO iface (device_id, name, kind) VALUES (?,?,?)",
                    (did, name, kind))
        iid = cur.lastrowid
        stats['ifaces'] += 1
    return iid

def link_exists(iid_a, iid_b):
    r = cur.execute("""
        SELECT id FROM link
        WHERE (a_iface_id=? AND b_iface_id=?)
           OR (a_iface_id=? AND b_iface_id=?)
    """, (iid_a, iid_b, iid_b, iid_a)).fetchone()
    return r is not None

def ensure_link(hostname_a, port_a, hostname_b, port_b):
    iid_a = ensure_iface(hostname_a, port_a)
    iid_b = ensure_iface(hostname_b, port_b)
    if not link_exists(iid_a, iid_b):
        cur.execute("INSERT INTO link (a_iface_id, b_iface_id) VALUES (?,?)", (iid_a, iid_b))
        stats['links'] += 1
        return True
    return False

# ── 1. New devices ─────────────────────────────────────────────────────────

print("\n=== 1. New devices ===")
ensure_device('POL90-30008-FREIA', 'switch', 'Main distribution switch, room 30008, 48 ports')
ensure_device('sw-loc-elLab',      'switch', 'Unmanaged 8-port D-Link switch, electronics lab (cable 07-927)')
ensure_device('outlet-30000',      'outlet', 'FREIA bunker wall outlets')

# ifaces for POL90 (ports 1-48)
print("  + ifaces  POL90-30008-FREIA ports 1-48")
for p in range(1, 49):
    ensure_iface('POL90-30008-FREIA', str(p))

# ifaces for sw-loc-elLab (8 ports)
print("  + ifaces  sw-loc-elLab ports 1-8")
for p in range(1, 9):
    ensure_iface('sw-loc-elLab', str(p))

# ifaces for outlet-30000 (ports 1-2 known from FREIA bunker section)
print("  + ifaces  outlet-30000 ports 1-2")
for p in range(1, 3):
    ensure_iface('outlet-30000', str(p))

# ── 2. Extend patch panels to 24 ports ────────────────────────────────────

print("\n=== 2. Extend panels to 24 ports ===")
# patch-panel-31A: add ports 13-24 (01-12 already exist)
print("  Extending patch-panel-31A ports 13-24")
for p in range(13, 25):
    ensure_iface('patch-panel-31A', str(p).zfill(2))

# patch-panel-11D: add ports 02-24 (01 already exists)
print("  Extending patch-panel-11D ports 02-24")
for p in range(2, 25):
    ensure_iface('patch-panel-11D', str(p).zfill(2))

# ── 3. Fix 31A:12 back-link ───────────────────────────────────────────────

print("\n=== 3. Fix patch-panel-31A:12 back-link ===")
iid_31a12  = get_iface_id('patch-panel-31A', '12')
iid_out5   = get_iface_id('outlet-30101', '5')
# Delete wrong link
if iid_31a12 and iid_out5:
    r = cur.execute("""
        DELETE FROM link
        WHERE (a_iface_id=? AND b_iface_id=?)
           OR (a_iface_id=? AND b_iface_id=?)
    """, (iid_31a12, iid_out5, iid_out5, iid_31a12))
    if r.rowcount:
        stats['fixes'] += 1
        print("  - removed: patch-panel-31A:12 ↔ outlet-30101:5")
# Add correct link
ensure_iface('outlet-30101', '6')
added = ensure_link('patch-panel-31A', '12', 'outlet-30101', '6')
if added:
    print("  + added:   patch-panel-31A:12 ↔ outlet-30101:6")

# ── 4. Additional back-port links (newly known connections) ───────────────

print("\n=== 4. Additional back-port links ===")

# FREIA bunker (from POL90 CSV bottom section)
print("  11D:02 ↔ outlet-30000:1")
ensure_link('patch-panel-11D', '02', 'outlet-30000', '1')
print("  11D:03 ↔ outlet-30000:2")
ensure_link('patch-panel-11D', '03', 'outlet-30000', '2')

# 11D:11 → 30007:34 (from POL90 CSV row 24, end connection field)
print("  11D:11 ↔ outlet-30007:34")
ensure_iface('outlet-30007', '34')
ensure_link('patch-panel-11D', '11', 'outlet-30007', '34')

# 11D:24 back → sw-loc-elLab:1 (electronics lab switch is at the outlet)
print("  11D:24 ↔ sw-loc-elLab:1")
ensure_link('patch-panel-11D', '24', 'sw-loc-elLab', '1')

# ── 5. Front-port links: patch panels → POL90-30008-FREIA ─────────────────

print("\n=== 5. POL90-30008-FREIA front-port links ===")

POL90_LINKS = [
    # (switch_port, panel_id, panel_port)
    ('1',  '21D', '19'),
    ('2',  '21D', '06'),
    ('3',  '21D', '05'),
    ('4',  '31A', '10'),
    ('5',  '11A', '02'),
    ('6',  '11A', '21'),
    ('7',  '21D', '04'),
    ('8',  '31A', '04'),
    # port 9: direct patch cable to PHY-YONNE PC, skip
    ('10', '11B', '15'),
    ('11', '21D', '15'),
    ('12', '21D', '11'),
    ('13', '11D', '01'),
    ('14', '21D', '09'),
    ('15', '11B', '24'),
    ('16', '11B', '14'),
    ('17', '31A', '01'),
    ('18', '21D', '13'),
    ('19', '21D', '23'),
    ('20', '11A', '03'),
    ('21', '31A', '09'),
    ('22', '31A', '07'),
    ('23', '21D', '03'),
    ('24', '11D', '11'),
    # ports 25-36: NC
    ('37', '31A', '05'),  # NC device but physical cable exists
    # port 38: NC
    ('39', '11B', '12'),
    ('40', '21D', '07'),
    # port 41: C0-1-31A-07 is duplicate/typo of port 22 (31A:07), skip
    ('42', '21D', '21'),
    ('43', '31A', '08'),
    ('44', '11B', '06'),
    ('45', '11D', '24'),
    ('46', '31A', '03'),
    ('47', '21D', '17'),
    # port 48: direct patch cable to freia-router WAN 1, skip
]

for sw_port, panel_id, panel_port in POL90_LINKS:
    panel_hostname = f'patch-panel-{panel_id}'
    panel_port_padded = panel_port.zfill(2)
    added = ensure_link('POL90-30008-FREIA', sw_port, panel_hostname, panel_port_padded)
    if added:
        print(f"  + POL90:{sw_port:>2s} ↔ {panel_hostname}:{panel_port_padded}")

# ── 6. Front-port links: patch panels → sw-loc-1 ─────────────────────────

print("\n=== 6. sw-loc-1 front-port links ===")

SWLOC1_LINKS = [
    # (sw_port, panel_id, panel_port)
    ('17', '21D', '01'),
    ('18', '21D', '20'),
    ('19', '21D', '18'),
    ('21', '31A', '11'),
]

for sw_port, panel_id, panel_port in SWLOC1_LINKS:
    panel_hostname = f'patch-panel-{panel_id}'
    panel_port_padded = panel_port.zfill(2)
    added = ensure_link('sw-loc-1', sw_port, panel_hostname, panel_port_padded)
    if added:
        print(f"  + sw-loc-1:{sw_port} ↔ {panel_hostname}:{panel_port_padded}")

# ── 7. Cross-patch link: 31A:12 front → 11D:07 ───────────────────────────

print("\n=== 7. Cross-patch 31A:12 ↔ 11D:07 ===")
added = ensure_link('patch-panel-31A', '12', 'patch-panel-11D', '07')
if added:
    print("  + patch-panel-31A:12 ↔ patch-panel-11D:07")
else:
    print("  already exists")

# ── Commit & report ────────────────────────────────────────────────────────

con.commit()
con.close()

con2 = sqlite3.connect(DB)
devices = con2.execute("SELECT count(*) FROM device").fetchone()[0]
ifaces  = con2.execute("SELECT count(*) FROM iface").fetchone()[0]
links   = con2.execute("SELECT count(*) FROM link").fetchone()[0]
con2.close()

print(f"""
=== Done ===
  New devices:  {stats['devices']}
  New ifaces:   {stats['ifaces']}
  New links:    {stats['links']}
  Fixed links:  {stats['fixes']}

DB totals: devices={devices}, ifaces={ifaces}, links={links}
""")
