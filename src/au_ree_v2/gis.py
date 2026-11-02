"""Recalculate projected GIS distances from complete versioned official layers."""
import json
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import transform
from pyproj import Transformer
from .store import canonical, issue

PROJECT = Transformer.from_crs(4326, 3577, always_xy=True).transform

def geometry(feature):
    g = feature.get('geometry') or {}
    if 'x' in g:
        return Point(g['x'], g['y'])
    if 'paths' in g:
        return shape({'type':'MultiLineString', 'coordinates': g['paths']})
    if 'rings' in g:
        raise ValueError('ArcGIS polygon ring topology requires an explicit adapter')
    return shape(g)

def nearest(lon, lat, features):
    point = transform(PROJECT, Point(lon, lat))
    candidates = []
    for f in features:
        geom = geometry(f)
        if geom.is_empty or not geom.is_valid:
            raise ValueError('Invalid layer geometry; incomplete distance refused')
        candidates.append(point.distance(transform(PROJECT, geom)) / 1000)
    if not candidates:
        raise ValueError('Empty layer')
    return min(candidates)

def run(db, root, snapshots, run_id, project_ids):
    output = {}
    for s in snapshots:
        if s['kind'] != 'arcgis_gis':
            continue
        data = json.loads((Path(root) / s['path']).read_text(encoding='utf-8'))
        if data.get('spatialReference', {}).get('wkid') != 4326 or not data.get('inventory', {}).get('complete'):
            issue(db, None, s['sha256'], 'GIS_INCOMPLETE_OR_CRS', s['key'])
            continue
        for eid in project_ids:
            record = db.execute('''SELECT r.*,s.acquired_at FROM records r JOIN sources s ON r.source_sha=s.sha
                WHERE entity_id=? AND r.longitude IS NOT NULL AND r.latitude IS NOT NULL
                ORDER BY s.acquired_at DESC LIMIT 1''', (eid,)).fetchone()
            if record is None or record['longitude'] is None:
                continue
            try:
                distance = nearest(record['longitude'], record['latitude'], data['features'])
                variable = s['layer'] + '_distance_km'
                provenance = {'layer_sha256': s['sha256'], 'coordinate_source_sha256': record['source_sha'],
                              'method': 'EPSG:3577 Euclidean point-to-geometry km',
                              'limitation': 'Representative project point; not project footprint or network travel distance'}
                db.execute('INSERT OR REPLACE INTO derived VALUES(?,?,?,?,?)',
                           (run_id, eid, variable, distance, canonical(provenance)))
                output.setdefault(eid, {})[variable] = {'value': distance, **provenance}
            except Exception as exc:
                issue(db, eid, s['sha256'], 'GIS_FAILED', str(exc))
    return output
