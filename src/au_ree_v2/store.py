"""Single canonical evidence store. No human approval is inferred."""
import hashlib
import json
import sqlite3
from pathlib import Path

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources(
 sha TEXT PRIMARY KEY, source_key TEXT NOT NULL, url TEXT NOT NULL,
 publication_date TEXT, acquired_at TEXT NOT NULL, path TEXT NOT NULL,
 kind TEXT NOT NULL, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS entities(
 entity_id TEXT PRIMARY KEY, kind TEXT NOT NULL, native_namespace TEXT NOT NULL,
 native_id TEXT NOT NULL, UNIQUE(native_namespace,native_id));
CREATE TABLE IF NOT EXISTS records(
 entity_id TEXT REFERENCES entities, source_sha TEXT REFERENCES sources,
 name TEXT NOT NULL, state TEXT, longitude REAL, latitude REAL,
 deposit_type TEXT, activity TEXT, raw TEXT NOT NULL,
 PRIMARY KEY(entity_id,source_sha));
CREATE TABLE IF NOT EXISTS relations(
 relation_id TEXT PRIMARY KEY, parent_id TEXT REFERENCES entities,
 child_id TEXT REFERENCES entities, relation TEXT NOT NULL,
 effective_date TEXT NOT NULL, source_sha TEXT REFERENCES sources,
 locator TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(
 obs_id TEXT PRIMARY KEY, entity_id TEXT REFERENCES entities,
 variable TEXT NOT NULL, value REAL, unit TEXT, basis TEXT,
 scope TEXT NOT NULL, statement_id TEXT NOT NULL, category TEXT,
 effective_date TEXT NOT NULL, source_sha TEXT REFERENCES sources,
 locator TEXT NOT NULL, status TEXT NOT NULL, issues TEXT NOT NULL,
 raw TEXT NOT NULL, transform_version TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS review_queue(
 issue_id TEXT PRIMARY KEY, entity_id TEXT, source_sha TEXT,
 reason TEXT NOT NULL, details TEXT NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(
 run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, cutoff TEXT NOT NULL,
 code_version TEXT NOT NULL, config_sha TEXT NOT NULL,
 snapshot_sha TEXT NOT NULL, status TEXT NOT NULL, error TEXT);
CREATE TABLE IF NOT EXISTS derived(
 run_id TEXT REFERENCES runs, entity_id TEXT REFERENCES entities,
 variable TEXT NOT NULL, value REAL, provenance TEXT NOT NULL,
 PRIMARY KEY(run_id,entity_id,variable));
CREATE TABLE IF NOT EXISTS study_cases(
 case_id TEXT PRIMARY KEY,project_id TEXT REFERENCES entities,source_sha TEXT REFERENCES sources,
 effective_date TEXT NOT NULL,scope TEXT NOT NULL,stage INTEGER NOT NULL,
 endpoint TEXT NOT NULL,element TEXT NOT NULL,scale TEXT NOT NULL,
 status TEXT NOT NULL,raw TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS census_screen_index(
 candidate_id TEXT NOT NULL,source_sha TEXT REFERENCES sources,source_key TEXT NOT NULL,
 native_label TEXT,state TEXT,tier TEXT,source_ref TEXT,selection_entity_id TEXT REFERENCES entities,
 parent_candidate_id TEXT REFERENCES entities,raw TEXT NOT NULL,PRIMARY KEY(candidate_id,source_sha));
'''

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def filehash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def append_snapshots(path, entries):
    """Merge immutable additions under a short writer lock, never replace history.

    Discovery and acquisition may finish in either order. A stale in-memory
    manifest must not erase a different source captured while it was fetching.
    """
    import os,time,uuid
    path=Path(path);lock=path.with_suffix(path.suffix+'.lock');started=time.monotonic()
    while True:
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);break
        except FileExistsError:
            if time.monotonic()-started>30:raise TimeoutError('MANIFEST_WRITER_BUSY_RETRY_LATER')
            time.sleep(.05)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        manifest=json.loads(path.read_text(encoding='utf8'))
        identity=lambda s:(s['key'],s['sha256'],s.get('source_document_version'))
        known={identity(s) for s in manifest['snapshots']}
        for s in entries:
            if identity(s) not in known:manifest['snapshots'].append(s);known.add(identity(s))
        temporary.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
        os.replace(temporary,path)
        return manifest
    finally:
        os.close(fd);lock.unlink()
        if temporary.exists():temporary.unlink()

def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path,timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript(SCHEMA)
    # Access paths only: no logical data or historical schema contract changes.
    db.executescript('''
        CREATE INDEX IF NOT EXISTS observations_entity_window ON observations(entity_id,status,effective_date);
        CREATE INDEX IF NOT EXISTS records_source_entity ON records(source_sha,entity_id);
        CREATE INDEX IF NOT EXISTS relations_parent_kind ON relations(parent_id,relation);
        CREATE INDEX IF NOT EXISTS observations_source ON observations(source_sha);
    ''')
    return db

def entity(db, namespace, native_id, kind):
    # Names, ownership and locations can change without changing identity.
    if isinstance(native_id, float) and native_id.is_integer():
        native_id = int(native_id)
    eid = 'AU-' + digest([namespace, str(native_id)])[:20]
    existing = db.execute('SELECT kind FROM entities WHERE entity_id=?', (eid,)).fetchone()
    if existing and existing['kind'] != kind:
        raise ValueError('Entity type conflict; explicit relationship review required')
    db.execute('INSERT OR IGNORE INTO entities VALUES(?,?,?,?)', (eid, kind, namespace, str(native_id)))
    return eid

def issue(db, eid, sha, reason, details):
    db.execute('INSERT OR IGNORE INTO review_queue VALUES(?,?,?,?,?,?)',
               (digest([eid, sha, reason, details]), eid, sha, reason, details, 'OPEN'))

def logical_dump(db):
    tables = ('sources', 'entities', 'records', 'relations', 'observations', 'review_queue','study_cases','census_screen_index')
    return {t: sorted([dict(r) for r in db.execute('SELECT * FROM ' + t)], key=canonical) for t in tables}
