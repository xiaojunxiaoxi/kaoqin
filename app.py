import sqlite3
import os
from datetime import date, datetime
from flask import Flask, request, render_template, redirect, url_for, jsonify, g
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.config['DATABASE'] = os.environ.get('DATABASE_PATH',
                                         os.path.join(app.root_path, 'attendance.db'))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'changeme-in-production')
app.config['BASE_URL'] = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db_path = app.config['DATABASE']
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id INTEGER NOT NULL,
            wname TEXT NOT NULL DEFAULT '',
            work_date TEXT NOT NULL,
            location TEXT NOT NULL DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (worker_id) REFERENCES workers(id) ON DELETE CASCADE
        )
    """)
    db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_attendance_worker_date
        ON attendance(worker_id, work_date)
    """)
    # Recover missing columns when upgrading
    try:
        db.execute("ALTER TABLE attendance ADD COLUMN wname TEXT NOT NULL DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE attendance ADD COLUMN updated_at TEXT DEFAULT (datetime('now','localtime'))")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE workers ADD COLUMN created_at TEXT DEFAULT (datetime('now','localtime'))")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE)")
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()


# ─── PWA Support ────────────────────────────────────────────────────
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "工长考勤",
        "short_name": "考勤",
        "description": "装修工人考勤管理工具",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#f0f2f5",
        "theme_color": "#1a73e8",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
        ]
    })


@app.route('/sw.js')
def service_worker():
    js = """const CACHE = 'attendance-cache-v1';
self.addEventListener('install', e => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/'])));
    self.skipWaiting();
});
self.addEventListener('activate', e => {
    e.waitUntil(clients.claim());
});
self.addEventListener('fetch', e => {
    e.respondWith(
        caches.match(e.request).then(r => r || fetch(e.request).catch(() => r))
    );
});"""
    from flask import make_response
    resp = make_response(js)
    resp.headers['Content-Type'] = 'application/javascript'
    resp.headers['Service-Worker-Allowed'] = '/'
    return resp


# ─── Routes ─────────────────────────────────────────────────────────
@app.route('/')
def index():
    db = get_db()
    today = date.today().isoformat()
    workers = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
    checked_in = db.execute("""
        SELECT a.*, w.name as worker_name
        FROM attendance a JOIN workers w ON a.worker_id = w.id
        WHERE a.work_date = ?
        ORDER BY w.name
    """, (today,)).fetchall()
    checked_in_ids = {r['worker_id'] for r in checked_in}
    not_checked_in = [w for w in workers if w['id'] not in checked_in_ids]
    return render_template('index.html',
                           today=today,
                           checked_in=checked_in,
                           not_checked_in=not_checked_in)


@app.route('/workers', methods=['GET', 'POST'])
def workers():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        if name:
            db.execute("INSERT INTO workers (name, phone) VALUES (?, ?)", (name, phone))
            db.commit()
        return redirect(url_for('workers'))
    workers_list = db.execute(
        "SELECT w.*, (SELECT COUNT(*) FROM attendance a WHERE a.worker_id=w.id) as days_count "
        "FROM workers w ORDER BY w.name"
    ).fetchall()
    return render_template('workers.html', workers=workers_list)


@app.route('/workers/<int:worker_id>/delete', methods=['POST'])
def delete_worker(worker_id):
    db = get_db()
    db.execute("DELETE FROM workers WHERE id=?", (worker_id,))
    db.commit()
    return redirect(url_for('workers'))


@app.route('/checkin', methods=['GET', 'POST'])
def checkin():
    db = get_db()
    if request.method == 'POST':
        work_date = request.form.get('work_date', date.today().isoformat())
        worker_ids = request.form.getlist('worker_ids')
        location = request.form.get('location', '').strip()
        for wid in worker_ids:
            existing = db.execute(
                "SELECT id FROM attendance WHERE worker_id=? AND work_date=?",
                (wid, work_date)
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO attendance (worker_id, work_date, location) VALUES (?, ?, ?)",
                    (wid, work_date, location)
                )
            else:
                db.execute(
                    "UPDATE attendance SET location=? WHERE worker_id=? AND work_date=?",
                    (location, wid, work_date)
                )
        db.commit()
        return redirect(url_for('index'))
    today = date.today().isoformat()
    workers_list = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
    return render_template('checkin.html', today=today, workers=workers_list)


@app.route('/records')
def records():
    db = get_db()
    workers_list = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    worker_id = request.args.get('worker_id', '')
    query = """
        SELECT a.*, w.name as worker_name
        FROM attendance a JOIN workers w ON a.worker_id = w.id
        WHERE 1=1
    """
    params = []
    if date_from:
        query += " AND a.work_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND a.work_date <= ?"
        params.append(date_to)
    if worker_id:
        query += " AND a.worker_id = ?"
        params.append(worker_id)
    query += " ORDER BY a.work_date DESC, w.name"
    records_list = db.execute(query, params).fetchall()
    records_by_date = {}
    for r in records_list:
        d = r['work_date']
        if d not in records_by_date:
            records_by_date[d] = []
        records_by_date[d].append(r)
    return render_template('records.html',
                           records_by_date=records_by_date,
                           workers=workers_list,
                           date_from=date_from, date_to=date_to,
                           selected_worker=worker_id)


@app.route('/api/stats')
def api_stats():
    db = get_db()
    total_workers = db.execute("SELECT COUNT(*) as c FROM workers").fetchone()['c']
    total_days = db.execute("SELECT COUNT(DISTINCT work_date) as c FROM attendance").fetchone()['c']
    total_records = db.execute("SELECT COUNT(*) as c FROM attendance").fetchone()['c']
    return jsonify(total_workers=total_workers, total_days=total_days, total_records=total_records)


@app.route('/api/dates-with-attendance')
def api_dates_with_attendance():
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT work_date FROM attendance ORDER BY work_date DESC"
    ).fetchall()
    return jsonify([r['work_date'] for r in rows])




# **? REST API for Mobile App Sync ********************************?
@app.route('/api/locations', methods=['GET', 'POST'])
def api_locations():
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if name:
            try:
                db.execute("INSERT OR IGNORE INTO locations (name) VALUES (?)", (name,))
                db.commit()
                row = db.execute("SELECT * FROM locations WHERE name=?", (name,)).fetchone()
                return jsonify({'id': row['id'], 'name': row['name']}), 201
            except Exception as e:
                return jsonify({'error': str(e)}), 400
        return jsonify({'error': 'name required'}), 400
    rows = db.execute("SELECT * FROM locations ORDER BY name").fetchall()
    return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])


@app.route('/api/locations/<int:loc_id>', methods=['DELETE'])
def api_delete_location(loc_id):
    db = get_db()
    db.execute("DELETE FROM locations WHERE id=?", (loc_id,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/workers', methods=['GET', 'POST'])
def api_workers():
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        phone = data.get('phone', '')
        if name:
            c = db.execute("INSERT INTO workers (name, phone) VALUES (?, ?)", (name, phone))
            db.commit()
            row = db.execute("SELECT * FROM workers WHERE id=?", (c.lastrowid,)).fetchone()
            return jsonify({'id': row['id'], 'name': row['name'], 'phone': row['phone']}), 201
        return jsonify({'error': 'name required'}), 400
    rows = db.execute(
        "SELECT w.*, (SELECT COUNT(*) FROM attendance a WHERE a.worker_id=w.id) as days_count "
        "FROM workers w ORDER BY w.name"
    ).fetchall()
    return jsonify([{'id': r['id'], 'name': r['name'], 'phone': r['phone'], 'days_count': r['days_count']} for r in rows])


@app.route('/api/workers/<int:worker_id>', methods=['DELETE'])
def api_delete_worker(worker_id):
    db = get_db()
    db.execute("DELETE FROM workers WHERE id=?", (worker_id,))
    db.execute("DELETE FROM attendance WHERE worker_id=?", (worker_id,))
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/checkins', methods=['GET', 'POST', 'DELETE'])
def api_checkins():
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or {}
        work_date = data.get('date', date.today().isoformat())
        location = data.get('location', '')
        worker_ids = data.get('worker_ids', [])
        if not isinstance(worker_ids, list):
            worker_ids = [worker_ids]
        saved = []
        for wid in worker_ids:
            w = db.execute("SELECT name FROM workers WHERE id=?", (wid,)).fetchone()
            if not w:
                continue
            wname = w['name']
            existing = db.execute(
                "SELECT id FROM attendance WHERE worker_id=? AND work_date=?",
                (wid, work_date)
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE attendance SET location=?, wname=?, updated_at=datetime('now','localtime') WHERE worker_id=? AND work_date=?",
                    (location, wname, wid, work_date)
                )
            else:
                db.execute(
                    "INSERT INTO attendance (worker_id, wname, work_date, location) VALUES (?, ?, ?, ?)",
                    (wid, wname, work_date, location)
                )
            saved.append({'worker_id': wid, 'wname': wname, 'work_date': work_date, 'location': location})
        db.commit()
        return jsonify({'ok': True, 'saved': saved}), 201
    elif request.method == 'DELETE':
        data = request.get_json() or request.args
        worker_id = data.get('worker_id')
        work_date = data.get('date')
        if worker_id and work_date:
            db.execute("DELETE FROM attendance WHERE worker_id=? AND work_date=?", (worker_id, work_date))
            db.commit()
        return jsonify({'ok': True})
    date_str = request.args.get('date', date.today().isoformat())
    rows = db.execute("""
        SELECT a.*, w.name as worker_name
        FROM attendance a JOIN workers w ON a.worker_id = w.id
        WHERE a.work_date = ?
        ORDER BY w.name
    """, (date_str,)).fetchall()
    return jsonify([{
        'id': r['id'],
        'worker_id': r['worker_id'],
        'wname': r['wname'] or r['worker_name'],
        'work_date': r['work_date'],
        'location': r['location'],
        'notes': r['notes']
    } for r in rows])


@app.route('/api/checkins/batch', methods=['POST'])
def api_checkins_batch():
    db = get_db()
    data = request.get_json() or {}
    records = data.get('records', [])
    for rec in records:
        wid = rec.get('worker_id')
        wname = rec.get('wname', '')
        work_date = rec.get('work_date', date.today().isoformat())
        location = rec.get('location', '')
        if not wid:
            continue
        existing = db.execute(
            "SELECT id FROM attendance WHERE worker_id=? AND work_date=?",
            (wid, work_date)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE attendance SET location=?, wname=?, updated_at=datetime('now','localtime') WHERE worker_id=? AND work_date=?",
                (location, wname, wid, work_date)
            )
        else:
            db.execute(
                "INSERT INTO attendance (worker_id, wname, work_date, location) VALUES (?, ?, ?, ?)",
                (wid, wname, work_date, location)
            )
    db.commit()
    dates = set(r.get('work_date', date.today().isoformat()) for r in records)
    result = {}
    for d in dates:
        rows = db.execute("""
            SELECT a.*, w.name as worker_name
            FROM attendance a JOIN workers w ON a.worker_id = w.id
            WHERE a.work_date = ?
            ORDER BY w.name
        """, (d,)).fetchall()
        result[d] = [{
            'worker_id': r['worker_id'],
            'wname': r['wname'] or r['worker_name'],
            'work_date': r['work_date'],
            'location': r['location']
        } for r in rows]
    worker_rows = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
    return jsonify({
        'ok': True,
        'data_by_date': result,
        'workers': [{'id': r['id'], 'name': r['name'], 'phone': r['phone']} for r in worker_rows]
    })


@app.route('/api/sync', methods=['GET', 'POST'])
def api_sync():
    db = get_db()
    if request.method == 'POST':
        data = request.get_json() or {}
        server_workers = data.get('workers', [])
        for w in server_workers:
            name = w.get('name', '').strip()
            if not name:
                continue
            existing = db.execute("SELECT id FROM workers WHERE name=?", (name,)).fetchone()
            if existing:
                db.execute("UPDATE workers SET phone=? WHERE id=?", (w.get('phone', ''), existing['id']))
            else:
                db.execute("INSERT INTO workers (name, phone) VALUES (?, ?)", (name, w.get('phone', '')))
        records = data.get('records', [])
        for rec in records:
            wid = rec.get('worker_id')
            wname = rec.get('wname', '')
            work_date = rec.get('work_date', date.today().isoformat())
            location = rec.get('location', '')
            if not wid and wname:
                w = db.execute("SELECT id FROM workers WHERE name=?", (wname,)).fetchone()
                if w:
                    wid = w['id']
            if not wid:
                continue
            existing = db.execute(
                "SELECT id FROM attendance WHERE worker_id=? AND work_date=?",
                (wid, work_date)
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE attendance SET location=?, wname=?, updated_at=datetime('now','localtime') WHERE id=?",
                    (location, wname, existing['id'])
                )
            else:
                db.execute(
                    "INSERT INTO attendance (worker_id, wname, work_date, location) VALUES (?, ?, ?, ?)",
                    (wid, wname, work_date, location)
                )
        server_locs = data.get('locations', [])
        for loc in server_locs:
            name = loc.get('name', '').strip()
            if name:
                db.execute("INSERT OR IGNORE INTO locations (name) VALUES (?)", (name,))
        db.commit()
    worker_rows = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
    loc_rows = db.execute("SELECT * FROM locations ORDER BY name").fetchall()
    attend_rows = db.execute("""
        SELECT a.*, w.name as worker_name
        FROM attendance a JOIN workers w ON a.worker_id = w.id
        WHERE a.work_date >= date('now', '-90 days')
        ORDER BY a.work_date DESC
    """).fetchall()
    return jsonify({
        'ok': True,
        'workers': [{'id': r['id'], 'name': r['name'], 'phone': r['phone']} for r in worker_rows],
        'locations': [{'id': r['id'], 'name': r['name']} for r in loc_rows],
        'attendance': [{
            'worker_id': r['worker_id'],
            'wname': r['wname'] or r['worker_name'],
            'work_date': r['work_date'],
            'location': r['location']
        } for r in attend_rows]
    })


@app.route('/api/today', methods=['GET'])
def api_today():
    db = get_db()
    today_str = date.today().isoformat()
    workers = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
    checkins = db.execute("""
        SELECT a.*, w.name as worker_name
        FROM attendance a JOIN workers w ON a.worker_id = w.id
        WHERE a.work_date = ?
        ORDER BY w.name
    """, (today_str,)).fetchall()
    checked_in_ids = {r['worker_id'] for r in checkins}
    return jsonify({
        'date': today_str,
        'checked_in': [{
            'worker_id': r['worker_id'],
            'wname': r['wname'] or r['worker_name'],
            'location': r['location']
        } for r in checkins],
        'not_checked_in': [
            {'id': w['id'], 'name': w['name']}
            for w in workers if w['id'] not in checked_in_ids
        ],
        'checked_count': len(checkins),
        'total_count': len(workers)
    })


@app.route('/api/attendance/stats')
def api_attendance_stats():
    db = get_db()
    rows = db.execute(
        "SELECT wname as name, location as loc, COUNT(*) as days FROM attendance GROUP BY wname, location ORDER BY wname, location"
    ).fetchall()
    result = {}
    for r in rows:
        name = r['name']
        if name not in result:
            result[name] = []
        result[name].append({'location': r['loc'], 'days': r['days']})
    return jsonify(result)


@app.route('/api/ping')
def api_ping():
    return jsonify({'ok': True, 'message': '******', 'time': datetime.now().isoformat()})


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
    return response


@app.errorhandler(404)
def not_found(e):
    return render_template('base.html'), 404


@app.errorhandler(500)
def server_error(e):
    return "服务器内部错误，请稍后重试", 500


if __name__ == '__main__':
    init_db()
    import socket
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname + ".local")
    print("=" * 55)
    print("  ✅ 工人考勤系统已启动")
    print(f"  📍 本机:  http://127.0.0.1:5000")
    print(f"  📶 局域网: http://{local_ip}:5000")
    print(f"  ☁️  已配置云端地址: {app.config['BASE_URL']}")
    print("  📱 手机用浏览器打开局域网地址即可使用")
    print("  🔄 按 Ctrl+C 停止")
    print("=" * 55)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
