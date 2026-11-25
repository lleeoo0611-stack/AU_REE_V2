"""Coordinate and boundary rules shared by cadastral and statutory source readers."""

import math
import re

from pyproj import CRS, Geod, Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union


def summary_identifier_key(value):
    """Type and numeric identifier only, preserving WA district; no name match."""
    value=re.sub(r'\s+','',str(value)).upper()
    match=re.fullmatch(r'([A-Z]+)(\d+)(?:/(\d+))?',value)
    if not match:return value
    return (match[1],int(match[2]),int(match[3]) if match[3] else None)


def summary_tenement_centroid(features, source_crs, limit_m=25000, id_field=None):
    """Union ALL exact-matched tenements; measure ALL vertices after fallback."""
    crs=CRS.from_user_input(source_crs)
    to_ll=Transformer.from_crs(crs,7844,always_xy=True,allow_ballpark=False)
    geometries=[transform(to_ll.transform,shape(f['geometry'])) for f in features]
    if not geometries or any(g.is_empty or not g.is_valid or g.geom_type not in ('Polygon','MultiPolygon') for g in geometries):
        return dict(accepted=False,reason='INVALID_OR_MISSING_POLYGON')
    union=unary_union(geometries)
    minx,miny,maxx,maxy=union.bounds
    if not (110<=minx<=maxx<=155 and -45<=miny<=maxy<=-9):
        return dict(accepted=False,reason='OUTSIDE_AUSTRALIA_OR_CRS_ERROR')
    # Local equal-area projection avoids measuring longitude/latitude degrees.
    metric=CRS.from_proj4(f'+proj=laea +lat_0={(miny+maxy)/2} +lon_0={(minx+maxx)/2} +ellps=GRS80 +units=m +no_defs')
    forward=Transformer.from_crs(7844,metric,always_xy=True)
    backward=Transformer.from_crs(metric,7844,always_xy=True)
    native=[transform(forward.transform,g) for g in geometries]
    titles={}
    for index,(feature,geometry) in enumerate(zip(features,native)):
        key=summary_identifier_key(feature['properties'][id_field]) if id_field else index
        titles.setdefault(key,[]).append(geometry)
    title_geometries=[unary_union(parts) for parts in titles.values()]
    combined=unary_union(title_geometries);point=combined.centroid;method='TENEMENT_CENTROID'
    if not combined.covers(point):
        point=max(title_geometries,key=lambda g:g.area).centroid;method='LARGEST_TENEMENT_CENTROID'
        if not combined.covers(point):return dict(accepted=False,reason='LARGEST_TENEMENT_CENTROID_OUTSIDE_UNION')
    lon,lat=backward.transform(point.x,point.y)
    geod=Geod(ellps='GRS80')
    polygons=list(union.geoms) if union.geom_type=='MultiPolygon' else [union]
    vertices=[xy for p in polygons for ring in [p.exterior,*p.interiors] for xy in ring.coords]
    precision=max(geod.inv(lon,lat,x,y)[2] for x,y in vertices)
    if not math.isfinite(precision):raise ValueError('NONFINITE_PRECISION')
    return dict(accepted=precision<=limit_m,reason='ACCEPTED' if precision<=limit_m else 'TENEMENT_UNION_EXCEEDS_25KM',longitude=lon,latitude=lat,precision_m=precision,location_method=method,input_crs=crs.to_string(),input_datum=crs.datum.name,output_crs='EPSG:7844',metric_crs=metric.to_string())
