# FREIA LabNet Web

Flask web application for browsing and editing the FREIA control-room network device map.

## What's included

| File | Purpose |
|---|---|
| `app.py` | Flask application (all routes) |
| `templates/` | Jinja2 HTML templates |
| `labnet.db` | SQLite database (current state) |
| `requirements.txt` | Python dependencies |
| `labnet_web.service` | systemd unit file for production |

---

## Quick start (demo / dev)

```bash
# 1. Clone
git clone <repo-url> labnet_web
cd labnet_web

# 2. Create virtualenv and install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Run
python app.py
# → open http://localhost:5000
```

---

## Ubuntu server deployment (production)

### 1. Create a dedicated user

```bash
sudo useradd -r -s /usr/sbin/nologin labnet
```

### 2. Clone into /opt

```bash
sudo git clone <repo-url> /opt/labnet_web
sudo chown -R labnet:labnet /opt/labnet_web
```

### 3. Create virtualenv

```bash
cd /opt/labnet_web
sudo -u labnet python3 -m venv venv
sudo -u labnet venv/bin/pip install -r requirements.txt
```

### 4. Install and start the systemd service

```bash
sudo cp /opt/labnet_web/labnet_web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now labnet_web
sudo systemctl status labnet_web
```

The app listens on **port 5000** by default. Access it at `http://<server-ip>:5000`.

### 5. (Optional) Expose via nginx on port 80

```bash
sudo apt install nginx
```

Create `/etc/nginx/sites-available/labnet_web`:

```nginx
server {
    listen 80;
    server_name _;          # or your hostname / IP

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/labnet_web /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## Updating the database

The database file is `labnet.db` in the working directory. To replace it on the server:

```bash
# copy the new db to the server, then:
sudo systemctl stop labnet_web
sudo cp labnet.db /opt/labnet_web/labnet.db
sudo chown labnet:labnet /opt/labnet_web/labnet.db
sudo systemctl start labnet_web
```

> **Note:** The MySQL cable database (`cntrldoc`) is accessed read-only via the
> existing connection — it is not modified by this app.

---

## Port / firewall

If the server has `ufw` active:

```bash
sudo ufw allow 5000/tcp    # direct Flask access
# or
sudo ufw allow 80/tcp      # if using nginx
```
