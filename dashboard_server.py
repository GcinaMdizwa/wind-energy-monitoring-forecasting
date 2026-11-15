"""WindScope local research dashboard. Run: python dashboard_server.py"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

import wind_data

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('WINDSCOPE_STATE', ROOT/'local_state'))
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE/'workspace.sqlite'
app = FastAPI(docs_url=None, redoc_url=None)
sessions, jobs, attempts = {}, {}, {}
training_lock = threading.Lock()


def connection():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


with connection() as db:
    db.executescript('''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT UNIQUE, salt TEXT, password TEXT);
    CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, owner TEXT, name TEXT, lat REAL, lon REAL, rated_kw REAL, created TEXT);''')


@app.middleware('http')
async def local_boundary(request: Request, call_next):
    host = request.headers.get('host', '')
    if host not in ('localhost:8765', '127.0.0.1:8765', 'testserver'):
        return JSONResponse({'detail': 'Local access only.'}, status_code=403)
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        if origin and origin not in ('http://localhost:8765', 'http://127.0.0.1:8765', 'http://testserver'):
            return JSONResponse({'detail': 'Cross-origin request rejected.'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-site request rejected.'}, status_code=403)
        if int(request.headers.get('content-length', '0')) > 20_000:
            return JSONResponse({'detail': 'Request too large.'}, status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src https://www.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


def user(request):
    token = request.cookies.get('windscope_session', '')
    session = sessions.get(token)
    if not session or session['expires'] < time.time():
        sessions.pop(token, None)
        raise HTTPException(401, 'Please sign in to your local workspace.')
    return session


def project(request, pid):
    u = user(request)
    with connection() as db:
        row = db.execute('SELECT * FROM projects WHERE id=? AND owner=?', (pid, u['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'Project not found in this workspace.')
    return dict(row)


def model_dir(p):
    return STATE/'models'/p['id']


@app.get('/')
def index():
    return FileResponse(ROOT/'dashboard.html')


@app.get('/dashboard.css')
def css():
    return FileResponse(ROOT/'dashboard.css')


@app.get('/dashboard.js')
def js():
    return FileResponse(ROOT/'dashboard.js')


@app.get('/api/session')
def session(request: Request):
    u = user(request)
    return {'name': u['name'], 'guest': u.get('guest', False)}


@app.post('/api/auth/{action}')
async def auth(action: str, request: Request):
    if action not in ('register', 'login', 'demo'):
        raise HTTPException(404)
    payload = await request.json()
    if action == 'demo':
        uid, name, guest = 'local-demo', 'Research guest', True
    else:
        name = str(payload.get('name', '')).strip()
        password = str(payload.get('password', ''))
        if not 2 <= len(name) <= 60 or not 10 <= len(password) <= 128:
            raise HTTPException(400, 'Use a 2–60 character name and a password of 10–128 characters.')
        key = name.casefold()
        recent = [t for t in attempts.get(key, []) if t > time.time()-300]
        if len(recent) >= 10:
            raise HTTPException(429, 'Too many attempts. Please wait five minutes.')
        recent.append(time.time())
        attempts[key] = recent
        with connection() as db:
            row = db.execute('SELECT * FROM users WHERE name=? COLLATE NOCASE', (name,)).fetchone()
            if action == 'register':
                if row:
                    raise HTTPException(409, 'That local profile name already exists. Sign in instead.')
                salt, uid = secrets.token_hex(16), uuid.uuid4().hex
                digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()
                db.execute('INSERT INTO users VALUES (?,?,?,?)', (uid, name, salt, digest))
            else:
                if not row:
                    raise HTTPException(401, 'Name or password is incorrect.')
                digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(row['salt']), 310000).hex()
                if not hmac.compare_digest(row['password'], digest):
                    raise HTTPException(401, 'Name or password is incorrect.')
                uid, name = row['id'], row['name']
        guest = False
    old = request.cookies.get('windscope_session', '')
    sessions.pop(old, None)
    token = secrets.token_urlsafe(32)
    sessions[token] = {'id': uid, 'name': name, 'guest': guest, 'expires': time.time()+43200}
    response = JSONResponse({'name': name, 'guest': guest})
    response.set_cookie('windscope_session', token, httponly=True, samesite='strict', max_age=43200)
    return response


@app.post('/api/logout')
def logout(request: Request):
    sessions.pop(request.cookies.get('windscope_session', ''), None)
    response = JSONResponse({'ok': True})
    response.delete_cookie('windscope_session')
    return response


@app.get('/api/search')
def search(request: Request, q: str = ''):
    user(request)
    try:
        return {'results': wind_data.search(q)}
    except Exception:
        raise HTTPException(502, 'Place search is unavailable. You can enter coordinates instead.')


@app.get('/api/monitor')
def monitor(request: Request, lat: float, lon: float, rated_kw: float = 2000):
    user(request)
    if not 1 <= rated_kw <= 20000:
        raise HTTPException(400, 'Rated turbine capacity must be 1–20,000 kW.')
    try:
        return wind_data.monitor(lat, lon, rated_kw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        raise HTTPException(502, 'Weather provider unavailable. Retry shortly; no synthetic live values are substituted.')


@app.get('/api/projects')
def projects(request: Request):
    u = user(request)
    with connection() as db:
        rows = db.execute('SELECT * FROM projects WHERE owner=? ORDER BY created DESC', (u['id'],)).fetchall()
    return {'projects': [dict(r) for r in rows]}


@app.post('/api/projects')
async def save_project(request: Request):
    u = user(request)
    p = await request.json()
    try:
        lat, lon = wind_data.coordinates(p.get('lat'), p.get('lon'))
        rated = float(p.get('rated_kw', 2000))
        name = str(p.get('name', '')).strip()
        if not 1 <= rated <= 20000 or not 2 <= len(name) <= 100:
            raise ValueError('Enter a project name and a capacity between 1 and 20,000 kW.')
    except (TypeError, ValueError) as e:
        raise HTTPException(400, str(e))
    pid = uuid.uuid4().hex
    with connection() as db:
        count = db.execute('SELECT COUNT(*) FROM projects WHERE owner=?', (u['id'],)).fetchone()[0]
        if count >= 50:
            raise HTTPException(400, 'Local workspace limit: 50 projects.')
        db.execute('INSERT INTO projects VALUES (?,?,?,?,?,?,?)',
                   (pid, u['id'], name, lat, lon, rated, datetime.now(timezone.utc).isoformat()))
    return {'id': pid}


@app.get('/api/projects/{pid}/model')
def model_report(pid: str, request: Request):
    p = project(request, pid)
    file = model_dir(p)/'report.json'
    return {'report': json.loads(file.read_text(encoding='utf8')) if file.exists() else None,
            'job': next((j for j in reversed(list(jobs.values())) if j['project_id'] == pid), None)}


@app.post('/api/projects/{pid}/train')
async def train_model(pid: str, request: Request):
    p = project(request, pid)
    args = await request.json()
    architecture = args.get('architecture', 'hybrid')
    years, epochs = args.get('years', 1), args.get('epochs', 12)
    if architecture not in ('rnn', 'lstm', 'hybrid') or years not in (1,2,3,5) or type(epochs) is not int or not 2 <= epochs <= 40:
        raise HTTPException(400, 'Choose a supported model, history length and 2–40 epochs.')
    if not training_lock.acquire(blocking=False):
        raise HTTPException(409, 'A training run is active. Wait for it to finish.')
    jid = uuid.uuid4().hex
    job = {'id': jid, 'project_id': pid, 'state': 'running', 'stage': 'Downloading ERA5 history', 'epoch': 0, 'epochs': epochs}
    jobs[jid] = job
    def worker():
        try:
            from recurrent_forecast import train
            frame, metadata = wind_data.history(p['lat'], p['lon'], years)
            job['rows'] = len(frame)
            # Write to a separate run directory; replace active model only after successful training.
            run_dir = STATE/'runs'/jid
            report = train(frame, run_dir, metadata, architecture, epochs, lambda **kw: job.update(kw))
            import shutil
            target = model_dir(p)
            target.mkdir(parents=True, exist_ok=True)
            for filename in ('model.pt', 'report.json', 'last_window.csv'):
                shutil.copyfile(run_dir/filename, target/filename)
            job.update(state='complete', stage='Model ready', report=report)
        except Exception as e:
            job.update(state='failed', stage='Training stopped', error=str(e)[:300])
        finally:
            training_lock.release()
    threading.Thread(target=worker, daemon=True).start()
    return {'job': job}


@app.get('/api/projects/{pid}/predict')
def predict(pid: str, request: Request):
    p = project(request, pid)
    if training_lock.locked():
        raise HTTPException(409, 'Wait for the active training run before forecasting.')
    if not (model_dir(p)/'model.pt').exists():
        raise HTTPException(409, 'Train a model for this project first.')
    try:
        import pandas as pd
        from recurrent_forecast import predict as infer
        weather = wind_data.monitor(p['lat'], p['lon'], p['rated_kw'])
        rows = [r for r in weather['rows'] if not r['future']][-48:]
        frame = pd.DataFrame({'timestamp': [r['time'] for r in rows], 'wind_speed_mps': [r['speed'] for r in rows],
                              'wind_direction_deg': [r['direction'] for r in rows]})
        return infer(model_dir(p), frame, p['rated_kw'])
    except Exception as e:
        raise HTTPException(502, str(e)[:250])


if __name__ == '__main__':
    print('WindScope: http://localhost:8765 (local machine only)')
    uvicorn.run(app, host='127.0.0.1', port=8765, log_level='info')
