# FREIA LabNet Web

Web application for browsing and editing the FREIA control-room network device map.
Tracks devices, interfaces, patch cables, VLANs, and physical locations.

GitHub: https://github.com/freia-lab/labnet_web

---

## Repository structure

```
labnet_web/
├── app.py                  # Flask application — all routes and database logic
├── labnet.db               # SQLite database (devices, interfaces, links, VLANs)
├── requirements.txt        # Python dependencies (Flask)
├── labnet_web.service      # systemd unit file for running as a background service
├── README.md               # This file
└── templates/
    ├── base.html           # Shared page layout, navigation bar
    ├── index.html          # Dashboard — device counts by type
    ├── devices.html        # Device list with search and kind/status filters
    ├── device.html         # Single device — interfaces, link creation, inline editing
    ├── links.html          # All patch links — inline editing of cable type, status, notes
    ├── vlans.html          # VLAN list
    ├── switch.html         # Switch port map view
    ├── trace.html          # Network path trace between two devices
    ├── validate.html       # Data validation checks
    └── settings.html       # Manage device-kind and device-status dropdown values
```

---

## Quick start (local / development)

```bash
git clone https://github.com/freia-lab/labnet_web.git
cd labnet_web
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
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

- **Devices** — full device list; filter by name, kind, or status
- **Links** — all patch cables; click ✏ to edit cable type, status, notes
- **VLANs** — VLAN list with subnet assignments
- **Switch** — port map for a named switch
- **Trace** — network path from a device back to the core switch
- **Settings** — add or remove device-kind and device-status values

---

## Making updates

### Edit device / interface data in the UI

Navigate to a device page and use the inline forms to add interfaces, set IP addresses, assign VLANs, or create links. Changes are written immediately to `labnet.db` on the server.

### Update the database file

If you need to replace `labnet.db` entirely (for example after editing it on another machine):

```bash
sudo systemctl stop labnet_web
cp /path/to/new/labnet.db /home/marek/labnet_web/labnet.db
sudo systemctl start labnet_web
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

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LABNET_PATH` | `labnet.db` (same directory as `app.py`) | Path to the SQLite database |
| `FLASK_HOST` | `0.0.0.0` | Interface to listen on |
| `FLASK_PORT` | `5000` | Port to listen on |
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode (development only) |

