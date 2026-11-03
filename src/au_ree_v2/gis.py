"""Recalculate projected GIS distances from complete versioned official layers."""
import json
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
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
        try:
            geoms=[geometry(f) for f in data['features']]
            if not geoms or any(g.is_empty or not g.is_valid for g in geoms):raise ValueError('Empty or invalid layer geometry')
            projected=[transform(PROJECT,g) for g in geoms];tree=STRtree(projected)
        except Exception as exc:
            issue(db,None,s['sha256'],'GIS_FAILED',str(exc));continue
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
                point=transform(PROJECT,Point(record['longitude'],record['latitude']))
                distance=point.distance(projected[int(tree.nearest(point))])/1000
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


def national_deposit_port_distances(db, root, snapshots, run_id):
    """Descriptive national GA *deposit* GIS only, never a Project score.

    The GA ports layer is global with a verified complete ID inventory; project
    scoped road/rail/power AOIs cannot be reused for national deposit distances.
    """
    selected={s["key"]:s for s in snapshots}
    deposits=selected.get("ga_aimr")
    ports=selected.get("ga_ports")
    if not deposits or not ports:
        return []
    data=json.loads((Path(root)/ports["path"]).read_text(encoding="utf-8"))
    inv=data.get("inventory",{})
    if not (inv.get("complete") and inv.get("scope","global")=="global"
            and data.get("spatialReference",{}).get("wkid")==4326):
        issue(db,None,ports["sha256"],"DEPOSIT_PORT_GLOBAL_INVENTORY_MISSING",ports["key"])
        return []
    try:
        if not data.get("features"):
            raise ValueError("Empty verified global port layer")
        geometries=[]
        for f in data["features"]:
            g=geometry(f)
            if g.is_empty or not g.is_valid:
                raise ValueError("Invalid port geometry")
            geometries.append(transform(PROJECT,g))
    except (ValueError,KeyError,TypeError) as exc:
        issue(db,None,ports["sha256"],"DEPOSIT_PORT_GEOMETRY_INVALID",str(exc))
        return []
    rows=[]
    for r in db.execute("""SELECT e.entity_id,r.name,r.state,r.deposit_type,
                                  r.longitude,r.latitude,r.source_sha
                           FROM records r JOIN entities e USING(entity_id)
                           WHERE e.kind='DEPOSIT' AND r.source_sha=?
                           ORDER BY e.entity_id""",(deposits["sha256"],)):
        d=dict(r)
        output={"deposit_id":d["entity_id"],"deposit_name":d["name"],
                "state":d["state"],"deposit_type":d["deposit_type"],
                "longitude":d["longitude"],"latitude":d["latitude"],
                "deposit_source_sha256":d["source_sha"],
                "port_source_sha256":ports["sha256"],"distance_km":None,
                "status":"MISSING_OR_INVALID_COORDINATE",
                "method":"EPSG:3577 Euclidean deposit-point-to-port km",
                "interpretation":"Deposit locality only; not a Project entity or transport route"}
        if (d["longitude"] is not None and d["latitude"] is not None
            and 110<=d["longitude"]<=155 and -45<=d["latitude"]<=-9):
            p=transform(PROJECT,Point(d["longitude"],d["latitude"]))
            value=min(p.distance(g)/1000 for g in geometries)
            if value>=0 and value<float("inf"):
                output["distance_km"]=value
                output["status"]="OFFICIAL_DEPOSIT_GEOMETRY_DISTANCE"
                provenance={"deposit_source_sha256":d["source_sha"],
                            "port_source_sha256":ports["sha256"],
                            "method":output["method"],"source_kind":"DEPOSIT",
                            "limitation":output["interpretation"]}
                db.execute("INSERT OR REPLACE INTO derived VALUES(?,?,?,?,?)",
                           (run_id,d["entity_id"],"deposit_port_distance_km",value,canonical(provenance)))
        rows.append(output)
    return rows

def deposit_type_port_summary(rows):
    """Cross-sectional descriptive Aim C covariates; no geological inference."""
    from statistics import median
    grouped={}
    for r in rows:
        key=(r["state"] or "UNKNOWN",r["deposit_type"] or "UNKNOWN")
        grouped.setdefault(key,[]).append(r)
    output=[]
    for (state,deposit_type),group in sorted(grouped.items()):
        valid=sorted(r["distance_km"] for r in group if r["distance_km"] is not None)
        output.append({"state":state,"deposit_type":deposit_type,
                       "deposits_total":len(group),"deposits_with_port_distance":len(valid),
                       "median_port_distance_km":median(valid) if valid else None,
                       "min_port_distance_km":valid[0] if valid else None,
                       "max_port_distance_km":valid[-1] if valid else None,
                       "unit_of_analysis":"GA_DEPOSIT_NOT_MCDA_PROJECT",
                       "inference":"DESCRIPTIVE_ONLY_NO_RANK_DRIVER_TEST"})
    return output
