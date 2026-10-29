#!/usr/bin/env python3
"""
FREIA labnet – Flask web interface
Run:  python app.py
      LABNET_PATH=/path/to/labnet.db python app.py
"""
import os
import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, g

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
LABNET_PATH = os.environ.get('LABNET_PATH', str(BASE_DIR.parent / 'labnet.db'))

app = Flask(__name__)
app.secret_key = 'freia-labnet-secret'   # needed for flash messages

def get_enum(category):
    """Read enum values from DB, falling back to hardcoded defaults if table missing."""
    try:
        rows = query("SELECT value FROM enum_value WHERE category=? ORDER BY value", (category,))
        return [r['value'] for r in rows]
    except Exception:
        return []

def device_kinds():    return get_enum('device_kind')
def device_statuses(): return get_enum('device_status')
IFACE_KINDS = ['nic', 'port', 'bond', 'vlan', 'lo', 'other']

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(LABNET_PATH)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
    return db

@app.teardown_appcontext
def close_db(exc):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv

def execute(sql, args=()):
    db = get_db()
    db.execute(sql, args)
    db.commit()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    counts = {r['kind']: r['cnt'] for r in query(
        "SELECT kind, COUNT(*) as cnt FROM device GROUP BY kind ORDER BY cnt DESC")}
    totals = query(
        "SELECT COUNT(*) as devices FROM device")[0]['devices']
    ifaces  = query("SELECT COUNT(*) as n FROM iface")[0]['n']
    links   = query("SELECT COUNT(*) as n FROM link")[0]['n']
    switches = query(
        "SELECT hostname FROM device WHERE kind='switch' ORDER BY hostname")
    return render_template('index.html',
        counts=counts, totals=totals, ifaces=ifaces, links=links,
        switches=switches)


@app.route('/devices')
def devices():
    kind   = request.args.get('kind', '')
    status = request.args.get('status', 'active')
    q      = request.args.get('q', '').strip()

    sql = """
        SELECT d.id, d.hostname, d.kind, d.status, d.purpose,
               l.name as location
        FROM device d LEFT JOIN location l ON l.id = d.location_id
        WHERE 1=1
    """
    args = []
    if kind:
        sql += " AND d.kind = ?"; args.append(kind)
    if status:
        sql += " AND d.status = ?"; args.append(status)
    if q:
        sql += """ AND (d.hostname LIKE ? OR d.purpose LIKE ? OR d.notes LIKE ?
                       OR EXISTS (SELECT 1 FROM iface WHERE device_id=d.id AND ip LIKE ?))"""
        args += [f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%']
    sql += " ORDER BY d.hostname"

    devs = query(sql, args)
    return render_template('devices.html', devices=devs,
        kinds=device_kinds(), statuses=device_statuses(),
        sel_kind=kind, sel_status=status, q=q)


@app.route('/device/<int:dev_id>')
def device(dev_id):
    dev = query(
        "SELECT d.*, l.name as location_name FROM device d "
        "LEFT JOIN location l ON l.id=d.location_id WHERE d.id=?",
        (dev_id,), one=True)
    if not dev:
        flash('Device not found', 'danger')
        return redirect(url_for('devices'))

    ifaces = query(
        "SELECT i.*, v.vid, v.name as vlan_name FROM iface i "
        "LEFT JOIN vlan v ON v.id=i.vlan_id WHERE i.device_id=?"
        " ORDER BY CAST(i.name AS INTEGER), i.name",
        (dev_id,))

    # For each iface, find its link if any
    links = {}
    for iface in ifaces:
        lnk = query("""
            SELECT l.cable_nr, l.status, cr.type as cable_type,
                   CASE WHEN l.a_iface_id=? THEN l.b_iface_id ELSE l.a_iface_id END as remote_iface_id
            FROM link l LEFT JOIN cable_ref cr ON cr.nr=l.cable_nr
            WHERE l.a_iface_id=? OR l.b_iface_id=?
        """, (iface['id'], iface['id'], iface['id']), one=True)
        if lnk:
            remote = query(
                "SELECT i.name, d.hostname, d.id as dev_id FROM iface i "
                "JOIN device d ON d.id=i.device_id WHERE i.id=?",
                (lnk['remote_iface_id'],), one=True)
            links[iface['id']] = {'link': lnk, 'remote': remote}

    locations = query("SELECT id, name, building, rack FROM location ORDER BY name")
    vlans     = query("SELECT id, vid, name FROM vlan ORDER BY vid")
    all_devs  = query("SELECT id, hostname FROM device ORDER BY hostname")
    return render_template('device.html', dev=dev, ifaces=ifaces, links=links,
        kinds=device_kinds(), statuses=device_statuses(), iface_kinds=IFACE_KINDS,
        locations=locations, vlans=vlans, all_devs=all_devs)


@app.route('/device/<int:dev_id>/edit', methods=['POST'])
def device_edit(dev_id):
    hostname     = request.form['hostname'].strip()
    kind         = request.form['kind']
    status       = request.form['status']
    purpose      = request.form.get('purpose', '').strip()
    notes        = request.form.get('notes', '').strip()
    location_id  = request.form.get('location_id', '').strip() or None
    new_loc_name = request.form.get('new_location_name', '').strip()

    try:
        db = get_db()
        # Create a new location on-the-fly if a name was typed
        if new_loc_name:
            cur = db.execute(
                "INSERT INTO location (name) VALUES (?)", (new_loc_name,))
            db.commit()
            location_id = cur.lastrowid
        elif location_id:
            location_id = int(location_id)
        else:
            location_id = None

        db.execute(
            """UPDATE device SET hostname=?, kind=?, status=?, purpose=?, notes=?,
               location_id=? WHERE id=?""",
            (hostname or None, kind, status, purpose or None, notes or None,
             location_id, dev_id))
        db.commit()
        flash('Device updated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('device', dev_id=dev_id))


@app.route('/device/new', methods=['POST'])
def device_new():
    hostname = request.form.get('hostname', '').strip()
    kind     = request.form.get('kind', 'pc')
    status   = request.form.get('status', 'active')
    purpose  = request.form.get('purpose', '').strip() or None
    notes    = request.form.get('notes', '').strip() or None
    if not hostname:
        flash('Hostname is required.', 'danger')
        return redirect(url_for('devices'))
    try:
        db = get_db()
        cur = db.execute(
            "INSERT INTO device (hostname, kind, status, purpose, notes) VALUES (?,?,?,?,?)",
            (hostname, kind, status, purpose, notes))
        db.commit()
        new_id = cur.lastrowid
        flash(f'Device "{hostname}" created.', 'success')
        return redirect(url_for('device', dev_id=new_id))
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('devices'))


@app.route('/device/<int:dev_id>/delete', methods=['POST'])
def device_delete(dev_id):
    dev = query("SELECT hostname FROM device WHERE id=?", (dev_id,), one=True)
    if not dev:
        flash('Device not found.', 'danger')
        return redirect(url_for('devices'))
    # Safety: refuse if any interface has an active link
    linked = query("""
        SELECT COUNT(*) as n FROM link l
        WHERE l.a_iface_id IN (SELECT id FROM iface WHERE device_id=?)
           OR l.b_iface_id IN (SELECT id FROM iface WHERE device_id=?)
    """, (dev_id, dev_id), one=True)
    if linked and linked['n'] > 0:
        flash(f'Cannot delete "{dev["hostname"]}": it has {linked["n"]} active link(s). '
              'Remove the links first.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))
    try:
        db = get_db()
        db.execute("DELETE FROM iface WHERE device_id=?", (dev_id,))
        db.execute("DELETE FROM device WHERE id=?", (dev_id,))
        db.commit()
        flash(f'Device "{dev["hostname"]}" deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
        return redirect(url_for('device', dev_id=dev_id))
    return redirect(url_for('devices'))


@app.route('/iface/<int:iface_id>/edit', methods=['POST'])
def iface_edit(iface_id):
    dev_id   = int(request.form['dev_id'])
    name     = request.form.get('name', '').strip() or None
    mac      = request.form.get('mac', '').strip() or None
    ip       = request.form.get('ip', '').strip() or None
    notes    = request.form.get('notes', '').strip() or None
    vlan_id  = request.form.get('vlan_id', '').strip() or None
    if vlan_id:
        vlan_id = int(vlan_id)

    try:
        execute("UPDATE iface SET name=COALESCE(?,name), mac=?, ip=?, notes=?, vlan_id=? WHERE id=?",
                (name, mac, ip, notes, vlan_id, iface_id))
        flash('Interface updated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('device', dev_id=dev_id))


@app.route('/device/<int:dev_id>/iface/new', methods=['POST'])
def iface_new(dev_id):
    name  = request.form.get('name', '').strip()
    kind  = request.form.get('kind', 'nic')
    ip    = request.form.get('ip', '').strip() or None
    mac   = request.form.get('mac', '').strip() or None
    notes = request.form.get('notes', '').strip() or None
    if not name:
        flash('Interface name is required.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))
    try:
        execute("INSERT INTO iface (device_id, name, kind, ip, mac, notes) VALUES (?,?,?,?,?,?)",
                (dev_id, name, kind, ip, mac, notes))
        flash(f'Interface "{name}" added.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('device', dev_id=dev_id))


@app.route('/iface/<int:iface_id>/delete', methods=['POST'])
def iface_delete(iface_id):
    dev_id = int(request.form['dev_id'])
    iface  = query("SELECT name FROM iface WHERE id=?", (iface_id,), one=True)
    if not iface:
        flash('Interface not found.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))
    linked = query(
        "SELECT COUNT(*) as n FROM link WHERE a_iface_id=? OR b_iface_id=?",
        (iface_id, iface_id), one=True)
    if linked and linked['n'] > 0:
        flash(f'Cannot delete "{iface["name"]}": it has an active link. Remove the link first.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))
    try:
        execute("DELETE FROM iface WHERE id=?", (iface_id,))
        flash(f'Interface "{iface["name"]}" deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('device', dev_id=dev_id))


@app.route('/switch/<hostname>')
def switch_map(hostname):
    dev = query(
        "SELECT * FROM device WHERE hostname=?", (hostname,), one=True)
    if not dev:
        dev = query(
            "SELECT * FROM device WHERE hostname LIKE ? AND kind='switch' LIMIT 1",
            (f'%{hostname}%',), one=True)
    if not dev:
        flash(f'Switch "{hostname}" not found', 'danger')
        return redirect(url_for('index'))

    ports = query("""
        SELECT i.id, i.name, i.notes,
               l.cable_nr, l.status as link_status,
               ri.name as remote_port, rd.hostname as remote_host,
               rd.id as remote_dev_id, rd.kind as remote_kind,
               cr.type as cable_type
        FROM iface i
        LEFT JOIN link l ON (l.a_iface_id=i.id OR l.b_iface_id=i.id)
        LEFT JOIN iface ri ON ri.id = CASE
            WHEN l.a_iface_id=i.id THEN l.b_iface_id ELSE l.a_iface_id END
        LEFT JOIN device rd ON rd.id=ri.device_id
        LEFT JOIN cable_ref cr ON cr.nr=l.cable_nr
        WHERE i.device_id=? AND i.kind='port'
        ORDER BY CAST(i.name AS INTEGER)
    """, (dev['id'],))

    total  = len(ports)
    used   = sum(1 for p in ports if p['cable_nr'] is not None)
    free   = total - used

    return render_template('switch.html', dev=dev, ports=ports,
        total=total, used=used, free=free)


@app.route('/trace/<hostname>')
def trace(hostname):
    dev = query(
        "SELECT id, hostname FROM device WHERE hostname LIKE ? LIMIT 1",
        (f'%{hostname}%',), one=True)
    if not dev:
        flash(f'Device "{hostname}" not found', 'danger')
        return redirect(url_for('devices'))

    nic = query(
        "SELECT id, name FROM iface WHERE device_id=? AND kind='nic' LIMIT 1",
        (dev['id'],), one=True)
    if not nic:
        flash(f'{hostname} has no NIC interface', 'warning')
        return redirect(url_for('device', dev_id=dev['id']))

    hops = query("""
        WITH RECURSIVE path(cur_iface, depth, device_name, dev_id,
                            iface_name, cable_nr, cable_type, visited) AS (
            SELECT i.id, 0, d.hostname, d.id, i.name, NULL, NULL,
                   ',' || i.id || ','
            FROM iface i JOIN device d ON d.id=i.device_id WHERE i.id=?
            UNION ALL
            SELECT
                CASE WHEN l.a_iface_id=p.cur_iface THEN l.b_iface_id ELSE l.a_iface_id END,
                p.depth+1, d2.hostname, d2.id, i2.name, l.cable_nr, cr.type,
                p.visited || CASE WHEN l.a_iface_id=p.cur_iface
                    THEN l.b_iface_id ELSE l.a_iface_id END || ','
            FROM path p
            JOIN link l ON (l.a_iface_id=p.cur_iface OR l.b_iface_id=p.cur_iface)
                AND l.status != 'removed'
            JOIN iface i2 ON i2.id=CASE
                WHEN l.a_iface_id=p.cur_iface THEN l.b_iface_id ELSE l.a_iface_id END
            JOIN device d2 ON d2.id=i2.device_id
            LEFT JOIN cable_ref cr ON cr.nr=l.cable_nr
            WHERE p.depth < 15
              AND p.visited NOT LIKE '%,' || CASE
                WHEN l.a_iface_id=p.cur_iface THEN l.b_iface_id ELSE l.a_iface_id END || ',%'
        )
        SELECT depth, device_name, dev_id, iface_name, cable_nr, cable_type
        FROM path ORDER BY depth
    """, (nic['id'],))

    return render_template('trace.html', hostname=dev['hostname'], hops=hops)


@app.route('/iface/<int:iface_id>/link/set', methods=['POST'])
def iface_link_set(iface_id):
    dev_id          = int(request.form['dev_id'])
    remote_hostname = request.form.get('remote_hostname', '').strip()
    remote_port     = request.form.get('remote_port', '').strip()
    cable_nr        = request.form.get('cable_nr', '').strip() or None

    if not remote_hostname or not remote_port:
        flash('Remote device and port are required.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))

    remote_dev = query("SELECT id FROM device WHERE hostname=?", (remote_hostname,), one=True)
    if not remote_dev:
        flash(f'Device "{remote_hostname}" not found.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))

    remote_iface = query(
        "SELECT id FROM iface WHERE device_id=? AND name=?",
        (remote_dev['id'], remote_port), one=True)
    if not remote_iface:
        flash(f'Port "{remote_port}" not found on {remote_hostname}.', 'danger')
        return redirect(url_for('device', dev_id=dev_id))

    a, b = iface_id, remote_iface['id']
    existing = query(
        "SELECT id FROM link WHERE (a_iface_id=? AND b_iface_id=?) OR (a_iface_id=? AND b_iface_id=?)",
        (a, b, b, a), one=True)
    if existing:
        flash('Link already exists between these ports.', 'warning')
        return redirect(url_for('device', dev_id=dev_id))

    # Remove any existing link on either end first
    execute("DELETE FROM link WHERE a_iface_id=? OR b_iface_id=?", (iface_id, iface_id))
    execute("DELETE FROM link WHERE a_iface_id=? OR b_iface_id=?", (remote_iface['id'], remote_iface['id']))

    execute("INSERT INTO link (a_iface_id, b_iface_id, cable_nr) VALUES (?,?,?)",
            (a, b, cable_nr))
    flash(f'Linked to {remote_hostname}:{remote_port}.', 'success')
    return redirect(url_for('device', dev_id=dev_id))


@app.route('/iface/<int:iface_id>/link/delete', methods=['POST'])
def iface_link_delete(iface_id):
    dev_id = int(request.form['dev_id'])
    execute("DELETE FROM link WHERE a_iface_id=? OR b_iface_id=?", (iface_id, iface_id))
    flash('Link removed.', 'success')
    return redirect(url_for('device', dev_id=dev_id))



@app.route('/link/<int:link_id>/edit', methods=['POST'])
def link_edit(link_id):
    cable_nr   = request.form.get('cable_nr', '').strip() or None
    cable_type = request.form.get('cable_type', '').strip() or None
    status     = request.form.get('status', '').strip() or None
    notes      = request.form.get('notes', '').strip() or None

    # Convert cable_nr to int if provided
    if cable_nr:
        try:
            cable_nr = int(cable_nr)
        except ValueError:
            flash('Cable number must be an integer.', 'danger')
            return redirect(url_for('links'))

    try:
        execute("UPDATE link SET cable_nr=?, status=?, notes=? WHERE id=?",
                (cable_nr, status, notes, link_id))

        # Update or insert cable_ref type if we have a cable number
        if cable_nr is not None:
            existing = query("SELECT nr FROM cable_ref WHERE nr=?", (cable_nr,), one=True)
            if existing:
                execute("UPDATE cable_ref SET type=? WHERE nr=?", (cable_type, cable_nr))
            else:
                execute("INSERT INTO cable_ref (nr, type) VALUES (?, ?)", (cable_nr, cable_type))

        flash('Link updated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('links'))

@app.route('/link/<int:link_id>/delete', methods=['POST'])
def link_delete(link_id):
    try:
        execute("DELETE FROM link WHERE id=?", (link_id,))
        flash('Link deleted.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('links'))


@app.route('/api/device/<int:dev_id>/ifaces')
def api_device_ifaces(dev_id):
    from flask import jsonify
    ifaces = query("SELECT id, name, kind FROM iface WHERE device_id=? ORDER BY CAST(name AS INTEGER), name", (dev_id,))
    return jsonify([dict(r) for r in ifaces])


@app.route('/validate')
def validate():
    issues = []

    dup_ip = query("""
        SELECT i.ip, GROUP_CONCAT(d.hostname, ', ') as hosts
        FROM iface i JOIN device d ON d.id=i.device_id
        WHERE i.ip IS NOT NULL GROUP BY i.ip HAVING COUNT(*)>1
    """)
    for r in dup_ip:
        issues.append(('warning', 'Duplicate IP', f"{r['ip']} → {r['hosts']}"))

    dup_mac = query("""
        SELECT i.mac, GROUP_CONCAT(d.hostname, ', ') as hosts
        FROM iface i JOIN device d ON d.id=i.device_id
        WHERE i.mac IS NOT NULL GROUP BY i.mac HAVING COUNT(*)>1
    """)
    for r in dup_mac:
        issues.append(('warning', 'Duplicate MAC', f"{r['mac']} → {r['hosts']}"))

    orphans = query("""
        SELECT hostname FROM device
        WHERE id NOT IN (SELECT DISTINCT device_id FROM iface)
    """)
    for r in orphans:
        issues.append(('info', 'Orphan device (no interfaces)', r['hostname']))

    return render_template('validate.html', issues=issues)


@app.route('/vlans')
def vlans():
    vlan_list = query("SELECT * FROM vlan ORDER BY vid")
    members = {}
    for v in vlan_list:
        members[v['vid']] = query("""
            SELECT d.hostname, d.kind, d.id as dev_id, i.name as iface_name, i.ip
            FROM iface i JOIN device d ON d.id=i.device_id
            WHERE i.vlan_id=? ORDER BY d.hostname
        """, (v['id'],))
    return render_template('vlans.html', vlans=vlan_list, members=members)


@app.route('/links')
def links():
    switch     = request.args.get('switch', '').strip()
    cable_type = request.args.get('cable_type', '').strip()

    sql = """
        SELECT l.id, l.cable_nr, l.status, cr.type as cable_type,
               da.hostname as a_host, da.id as a_dev_id, ia.name as a_port,
               db.hostname as b_host, db.id as b_dev_id, ib.name as b_port
        FROM link l
        LEFT JOIN cable_ref cr ON cr.nr = l.cable_nr
        JOIN iface ia ON ia.id = l.a_iface_id
        JOIN device da ON da.id = ia.device_id
        JOIN iface ib ON ib.id = l.b_iface_id
        JOIN device db ON db.id = ib.device_id
        WHERE 1=1
    """
    args = []
    if switch:
        sql += " AND (da.hostname = ? OR db.hostname = ?)"
        args += [switch, switch]
    if cable_type:
        sql += " AND cr.type = ?"
        args.append(cable_type)
    sql += " ORDER BY l.cable_nr NULLS LAST, da.hostname"

    all_links   = query(sql, args)
    switches    = query("SELECT hostname FROM device WHERE kind='switch' ORDER BY hostname")
    cable_types = query("SELECT DISTINCT type FROM cable_ref WHERE type IS NOT NULL ORDER BY type")

    return render_template('links.html', links=all_links,
        switches=switches, cable_types=cable_types,
        sel_switch=switch, sel_cable_type=cable_type)



@app.route('/settings')
def settings():
    kinds    = query("SELECT id, value FROM enum_value WHERE category='device_kind'    ORDER BY value")
    statuses = query("SELECT id, value FROM enum_value WHERE category='device_status'  ORDER BY value")
    return render_template('settings.html', kinds=kinds, statuses=statuses)

@app.route('/settings/enum/add', methods=['POST'])
def enum_add():
    category = request.form['category']
    value    = request.form['value'].strip().lower().replace(' ', '_')
    if category not in ('device_kind', 'device_status'):
        flash('Invalid category.', 'danger')
        return redirect(url_for('settings'))
    if not value:
        flash('Value cannot be empty.', 'danger')
        return redirect(url_for('settings'))
    try:
        execute("INSERT INTO enum_value (category, value) VALUES (?, ?)", (category, value))
        flash(f'Added "{value}".', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'danger')
    return redirect(url_for('settings'))

@app.route('/settings/enum/<int:enum_id>/delete', methods=['POST'])
def enum_delete(enum_id):
    row = query("SELECT category, value FROM enum_value WHERE id=?", (enum_id,), one=True)
    if not row:
        flash('Not found.', 'danger')
        return redirect(url_for('settings'))
    # Warn if value is still in use
    col = 'kind' if row['category'] == 'device_kind' else 'status'
    count = query(f"SELECT COUNT(*) as n FROM device WHERE {col}=?", (row['value'],), one=True)['n']
    if count > 0:
        flash(f'Cannot delete "{row["value"]}" — still used by {count} device(s).', 'danger')
        return redirect(url_for('settings'))
    execute("DELETE FROM enum_value WHERE id=?", (enum_id,))
    flash(f'Removed "{row["value"]}".', 'success')
    return redirect(url_for('settings'))

# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'DB: {LABNET_PATH}')
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    host  = os.environ.get('FLASK_HOST', '0.0.0.0')
    port  = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(debug=debug, host=host, port=port)
