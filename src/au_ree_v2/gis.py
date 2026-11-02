"""Recalculate projected GIS distances from complete versioned official layers."""
import json
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import transform
from pyproj import Transformer
from .store import canonical, issue
from .spatial import covered_project

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

def representative_coordinate(db, eid, source_shas):
    """Use only cutoff-selected source records; prefer evidenced deposit anchors."""
    rows = db.execute('''SELECT r.longitude,r.latitude,r.source_sha,s.acquired_at,
        EXISTS(SELECT 1 FROM relations rel WHERE rel.parent_id=r.entity_id
               AND rel.source_sha=r.source_sha
               AND rel.relation='REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE') AS anchored
        FROM records r JOIN sources s ON r.source_sha=s.sha
        WHERE r.entity_id=? AND r.longitude IS NOT NULL AND r.latitude IS NOT NULL
        ORDER BY anchored DESC,s.acquired_at DESC,r.source_sha''',(eid,)).fetchall()
    for r in rows:
        if r['source_sha'] in source_shas:
            return dict(r)
    return None

def run(db, root, snapshots, run_id, project_ids):
    output = {}
    source_shas = {s['sha256'] for s in snapshots}
    for s in snapshots:
        if s['kind'] != 'arcgis_gis':
            continue
        data = json.loads((Path(root) / s['path']).read_text(encoding='utf-8'))
        inventory = data.get('inventory',{})
        if data.get('spatialReference',{}).get('wkid') != 4326 or not inventory.get('complete'):
            issue(db, None, s['sha256'], 'GIS_INCOMPLETE_OR_CRS', s['key'])
            continue
        if inventory.get('scope','global') not in ('global','registered_project_aoi'):
            issue(db,None,s['sha256'],'GIS_UNKNOWN_COVERAGE_SCOPE',s['key'])
            continue
        for eid in project_ids:
            record = representative_coordinate(db,eid,source_shas)
            if record is None:
                continue
            radius = None
            if inventory.get('scope') == 'registered_project_aoi':
                native = db.execute('SELECT native_id FROM entities WHERE entity_id=?',(eid,)).fetchone()
                if native is None:
                    continue
                coverage = covered_project(inventory,native['native_id'],
                                           record['longitude'], record['latitude'])
                if coverage is None:
                    issue(db,eid,s['sha256'],'GIS_AOI_NOT_COVERED',
                          canonical({'layer':s['key'],'coordinate_sha256':record['source_sha']}))
                    continue
                radius=coverage['radius_km']
            try:
                distance = nearest(record['longitude'], record['latitude'],data['features'])
                # AOI inventory proves only distances strictly inside the source radius.
                if radius is not None and distance >= radius - 0.0001:
                    issue(db,eid,s['sha256'],'GIS_NEAREST_OUTSIDE_AOI_RADIUS',
                          canonical({'distance_km':distance,'radius_km':radius}))
                    continue
                variable=s['layer']+'_distance_km'
                provenance={'layer_sha256':s['sha256'],
                            'coordinate_source_sha256':record['source_sha'],
                            'method':'EPSG:3577 Euclidean point-to-geometry km',
                            'source_where':inventory.get('where'),
                            'coverage_scope':inventory.get('scope','global'),
                            'radius_km':radius,
                            'limitation':'Representative point only; not footprint, route access, freight or grid availability'}
                db.execute('INSERT OR REPLACE INTO derived VALUES(?,?,?,?,?)',
                           (run_id,eid,variable,distance,canonical(provenance)))
                output.setdefault(eid,{})[variable]={'value':distance,**provenance}
            except Exception as exc:
                issue(db,eid,s['sha256'],'GIS_FAILED',str(exc))
    return output
