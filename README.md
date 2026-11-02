# FREIA LabNet Web

Web application for browsing and editing the FREIA control-room network device map.
Tracks devices, interfaces, patch cables, VLANs, physical locations, EPICS/OS services,
IP address modes (static/DHCP), and VM host relationships.

GitHub: https://github.com/freia-lab/labnet_web

---

## Repository structure

```
labnet_web/
├── app.py                  # Flask application — all routes and database logic
├── labnet.db               # SQLite database (devices, interfaces, links, VLANs, services)
├── requirements.txt        # Python dependencies (Flask)
├── labnet_web.service      # systemd unit file for running as a background service
├── import_services.py      # One-shot importer: loads service assignments from CSV
├── import_kea.py           # One-shot importer: syncs DHCP reservations from kea-dhcp4.conf
├── README.md               # This file
└── templates/
    ├── base.html           # Shared page layout, navigation bar
    ├── index.html          # Dashboard — device counts by type
    ├── devices.html        # Device list with search and kind/status filters
    ├── device.html         # Single device — interfaces, services, VM info, link creation
    ├── links.html          # All patch links — inline editing of cable type, status, notes
    ├── vlans.html          # VLAN list
    ├── switch.html         # Switch port map view
    ├── trace.html          # Network path trace between two devices
    ├── validate.html       # Data validation checks
    └── settings.html       # Manage device-kind, device-status, and service catalogue
```

---

## Features

### Device tracking
- Hostname, kind, status, vendor/model, OS, serial, owner, purpose, notes
- Physical location assignment
- **VM host**: mark a device as a virtual machine and record which physical host runs it;
  the host's page lists all its VMs

### Interface tracking
- NIC name, IP address, MAC address, VLAN assignment
- **IP mode**: `static` (default) or `dhcp` — DHCP interfaces show an amber badge on the
  device page; sourced from kea-dhcp4 reservations or set manually
- Trunk VLAN lists for switch ports

### Service tracking
- Per-device EPICS and OS service assignments with an optional role field
- Service catalogue managed in Settings; usage counts shown per service
- Bulk-import from `FREIA_network_devicesIP.csv` with `import_services.py`

### Search and filter
- Device list searchable by hostname, MAC address, IP, vendor/model, serial, owner, purpose
- Filter by kind and status

---

## Quick start (local / development)

```bash
git clone https://github.com/freia-lab/labnet_web.git
cd labnet_web
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
LABNET_PATH=/path/to/labnet.db python app.py
```

Open http://localhost:5000 in a browser.

---

## Current deployment

| Item | Value |
|---|---|
| Server | freia-ub3 |
| User | marek |
| Path | `/home/marek/labnet_web` |
| Service | `labnet_web.service` (systemd) |
| URL | http://192.168.10.72:5000 |

The application runs as a systemd service and starts automatically on boot.

**Check status / logs:**

```bash
sudo systemctl status labnet_web
journalctl -u labnet_web -f
```

**Start / stop / restart:**

```bash
sudo systemctl start labnet_web
sudo systemctl stop labnet_web
sudo systemctl restart labnet_web
```

---

## Accessing the web UI

From any machine on the FREIA lab network:

```
http://192.168.10.72:5000
```

Main sections (navigation bar):

- **Devices** — full device list; filter by name, kind, or status; search includes MAC address
- **Links** — all patch cables; click ✏ to edit cable type, status, notes
- **VLANs** — VLAN list with subnet assignments
- **Switch** — port map for a named switch
- **Trace** — network path from a device back to the core switch
- **Settings** — manage device-kind, device-status values, and the service catalogue

---

## Making updates

### Edit device / interface data in the UI

Navigate to a device page and use the inline forms to add interfaces, set IP addresses,
assign VLANs, manage services, or create links. Changes are written immediately to
`labnet.db` on the server.

### Deploy a new database to freia-ub3

After editing `labnet.db` locally, copy it to the server and restart:

```bash
sudo systemctl stop labnet_web
scp /path/to/labnet.db marek@192.168.10.72:/home/marek/labnet_web/labnet.db
ssh marek@192.168.10.72 'sudo systemctl start labnet_web'
```

### Update the application code

On freia-ub3:

```bash
cd ~/labnet_web
git pull
sudo systemctl restart labnet_web
```

### Push a code change from your workstation

Edit the files in your local clone, then:

```bash
git add -A
git commit -m "Describe what changed"
git push
```

Then on freia-ub3 run `git pull && sudo systemctl restart labnet_web`.

---

## One-shot importers

### import_services.py — load EPICS/OS service assignments from CSV

```bash
python3 import_services.py [path/to/labnet.db] [path/to/FREIA_network_devicesIP.csv]
```

Reads the EPICS service columns (9–22) and OS service columns (24–38) from the CSV,
matches rows by hostname, and inserts `device_service` assignments. Safe to re-run
(uses `INSERT OR IGNORE`). Requires the `service` catalogue to be populated first
(via Settings → Service catalogue in the UI).

### import_kea.py — sync DHCP reservations from kea-dhcp4.conf

```bash
python3 import_kea.py [path/to/labnet.db] [path/to/kea-dhcp4.conf]
```

Reads `kea-dhcp4.conf` (Kea DHCP4 JSON format), finds all reservations, and for each:

- Sets `ip_mode = 'dhcp'` on the matching interface
- Fills in the MAC address if the interface has none
- Devices in the dynamic pool ranges are also marked as `ip_mode = 'dhcp'`

Prompts before overwriting a conflicting MAC. Devices present in kea but not in the
database are reported; pass `--create` to add them as stub devices.

---

## Database schema highlights

```sql
-- Core tables (unchanged)
device   (id, hostname, kind, status, vendor_model, os, serial, location_id,
           owner, purpose, notes, vm_host_id)   -- vm_host_id: FK → device.id
iface    (id, device_id, name, kind, mac, ip, prefix, vlan_id, notes,
           mode, ip_mode)                         -- ip_mode: 'static'|'dhcp'
link     (id, iface_a, iface_b, cable_type, status, notes, trunk_vlans)

-- Service tracking
service        (id, name, category)              -- category: 'epics'|'os'
device_service (id, device_id, service_id, role, notes)
```

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LABNET_PATH` | `labnet.db` (same directory as `app.py`) | Path to the SQLite database |
| `FLASK_HOST` | `0.0.0.0` | Interface to listen on |
| `FLASK_PORT` | `5000` | Port to listen on |
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode (development only) |
