"""Project-scoped, projected ArcGIS query windows with explicit coverage limits.

A window encloses the EPSG:3577 radius, and an inventory-complete ArcGIS
spatial query proves nearest proximity only when the returned distance is
strictly inside that radius. No legal road, rail or power access is inferred.
"""
import json
from pathlib import Path
from pyproj import Transformer
from .store import filehash

_TO = Transformer.from_crs(4326, 3577, always_xy=True)
_FROM = Transformer.from_crs(3577, 4326, always_xy=True)

def bounding_window(lon, lat, radius_km):
    if not (110 <= lon <= 155 and -45 <= lat <= -9 and 0 < radius_km <= 1000):
        raise ValueError('Invalid project point or AOI radius')
    x, y = _TO.transform(lon, lat)
    r = radius_km * 1000.0
    samples = []
    # Sampling the boundary of a bounding square is deliberately conservative.
    for k in range(17):
        t = -r + 2 * r * k / 16
        samples.extend(((x-r, y+t), (x+r, y+t), (x+t, y-r), (x+t, y+r)))
    coords = [_FROM.transform(a, b) for a, b in samples]
    return [min(p[0] for p in coords), min(p[1] for p in coords),
            max(p[0] for p in coords), max(p[1] for p in coords)]

def project_windows(root, manifest, radius_km):
    """Only evidenced project-to-deposit anchors; do not equate deposits with projects."""
    root = Path(root)
    claims = json.loads((root/'data/claims.json').read_text(encoding='utf-8'))
    available = {}
    for s in manifest['snapshots']:
        if s['kind'] != 'arcgis_census':
            continue
        if s['key'] not in available or s['acquired_at'] > available[s['key']]['acquired_at']:
            available[s['key']] = s
    positions = {}
    for key, s in available.items():
        path = root/s['path']
        if filehash(path) != s['sha256']:
            raise ValueError('AOI anchor source checksum mismatch')
        data = json.loads(path.read_text(encoding='utf-8'))
        for f in data['features']:
            attrs = f['attributes']
            native = attrs.get(s['id_field'])
            if native is None:
                continue
            g = f.get('geometry') or {}
            lon = attrs.get('longitude', g.get('x'))
            lat = attrs.get('latitude', g.get('y'))
            if lon is not None and lat is not None:
                positions[(key, str(native))] = (float(lon), float(lat), s['sha256'])
    out = []
    for p in sorted(claims['projects'], key=lambda v: v['id']):
        anchor = positions.get((p.get('coordinate_source'), str(p.get('coordinate_native_id'))))
        if anchor is None:
            continue
        lon, lat, sha = anchor
        out.append({'project_id':p['id'], 'longitude':lon, 'latitude':lat,
                    'radius_km':radius_km, 'bbox':bounding_window(lon, lat, radius_km),
                    'coordinate_source_sha256':sha})
    if not out:
        raise ValueError('No source-anchored registered project coordinates; AOI acquisition refused')
    return out

def covered_project(inventory, project_id, lon, lat):
    for q in inventory.get('queries', []):
        if (q.get('project_id') == project_id and
            abs(q['longitude'] - lon) < 1e-5 and abs(q['latitude'] - lat) < 1e-5):
            return q
    return None
