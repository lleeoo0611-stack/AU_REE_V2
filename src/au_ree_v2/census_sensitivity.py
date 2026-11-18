"""Fixed-cohort sensitivity to source-supported Census point alternatives."""
from collections import defaultdict
from math import isclose

from pyproj import Transformer

from .analysis import interval_mcda, read_csv as read_rows, score, write_csv
from .gis import representative_coordinate, run as gis_run


def compare_gis_points(db, root, out, run_id, snapshots, gis_values, identity, config, panels):
    points = {r['project_id']: r for r in read_rows(out/'project-summary'/'spatial_point_quality.csv')}
    shas = {s['sha256'] for s in snapshots}
    alternatives, distances = {}, {}
    for eid, metrics in sorted(gis_values.items()):
        pid = identity['mapping'].get(eid, eid)
        alternative = points.get(pid, {})
        baseline = representative_coordinate(db, eid, shas)
        crs = alternative.get('export_crs')
        kind = alternative.get('point_role')
        verified = alternative.get('method') not in ('NORMALIZED_NAME_MATCH', '')
        base = dict(project_id=eid, canonical_project_id=pid,
                    baseline_source_sha256=(baseline or {}).get('source_sha'),
                    alternative_source_sha256=alternative.get('source_sha256'), point_role=kind,
                    alternative_locator=alternative.get('locator'), alternative_crs=crs)
        for variable, value in metrics.items():
            distances[eid, variable] = dict(base, variable=variable, baseline_km=value['value'],
                                          status='NO_DISTINCT_SCOPE_VERIFIED_ALTERNATIVE')
        if not (verified and baseline and crs and alternative.get('longitude') and alternative.get('latitude')):
            continue
        src_crs = {'GDA94': 'EPSG:4283', 'GDA2020': 'EPSG:7844'}.get(crs, crs)
        if src_crs.isdigit():
            src_crs = 'EPSG:' + src_crs
        transformer = Transformer.from_crs(src_crs, 'EPSG:4326', always_xy=True, allow_ballpark=False)
        lon, lat = transformer.transform(float(alternative['longitude']), float(alternative['latitude']), errcheck=True)
        if isclose(lon, baseline['longitude'], abs_tol=1e-5) and isclose(lat, baseline['latitude'], abs_tol=1e-5):
            continue
        alternatives[eid] = dict(longitude=lon, latitude=lat, source_sha=alternative['source_sha256'])
        for variable in metrics:
            distances[eid, variable]['status'] = 'ALTERNATIVE_OUTSIDE_VERIFIED_LAYER_COVERAGE'
    recalculated = gis_run(db, root, snapshots, run_id, alternatives, alternative_points=alternatives) if alternatives else {}
    for (eid, variable), row in distances.items():
        if metric := recalculated.get(eid, {}).get(variable):
            if metric['layer_sha256'] == gis_values[eid][variable]['layer_sha256']:
                row.update(status='COMPARED_ON_SAME_LAYER', alternative_km=metric['value'],
                           delta_km=metric['value']-row['baseline_km'])
    write_csv(out/'census_gis_sensitivity.csv', distances.values(), (
        'project_id', 'canonical_project_id', 'variable', 'baseline_source_sha256',
        'alternative_source_sha256', 'point_role', 'alternative_locator', 'alternative_crs',
        'baseline_km', 'alternative_km', 'delta_km', 'status'))
    rank_variants(out, config, panels, distances)


def rank_variants(out, config, panels, distances):
    changed = {k: r for k, r in distances.items() if r['status']=='COMPARED_ON_SAME_LAYER'}
    criteria = {c['code']: c for c in config['criteria'] if c['domain']=='Infrastructure'}
    output = []
    for panel in sorted(panels):
        folder = out/panel
        rows = read_rows(folder/'matrix.csv')
        codes = [r['code'] for r in read_rows(folder/'criteria.csv')]
        if not criteria.keys() & set(codes) or len(rows)<2:
            continue
        weights = defaultdict(dict)
        for definition in read_rows(folder/'weights.csv'):
            weights[definition['scenario']][definition['criterion']] = float(definition['weight'])
        baseline, variant, affected = [], [], set()
        for row in rows:
            original = [float(row[code]) for code in codes]
            revised = original.copy()
            for i, code in enumerate(codes):
                criterion = criteria.get(code)
                if not criterion:
                    continue
                change = changed.get((row['project_id'], criterion['variable']))
                if change and isclose(original[i], score(change['baseline_km'], criterion), abs_tol=1e-12):
                    revised[i] = score(change['alternative_km'], criterion)
                    affected.add(row['project_id'])
            baseline.append([(v,v) for v in original])
            variant.append([(v,v) for v in revised])
        if not affected:
            output.append(dict(panel=panel, cohort_size=len(rows), status='NO_VERIFIED_COMPARABLE_POINT_PAIR_IN_PANEL'))
            continue
        for scenario, weights_by_code in sorted(weights.items()):
            vector = [weights_by_code[code] for code in codes]
            before = interval_mcda(baseline, vector, config['promethee_threshold'])
            after = interval_mcda(variant, vector, config['promethee_threshold'])
            for method, ranks in before.items():
                for row, original, revised in zip(rows, ranks, after[method]):
                    output.append(dict(panel=panel, scenario=scenario, method=method, project_id=row['project_id'],
                        cohort_size=len(rows), point_changed=int(row['project_id'] in affected),
                        baseline_best=original['rank_best'], baseline_worst=original['rank_worst'],
                        alternative_best=revised['rank_best'], alternative_worst=revised['rank_worst'],
                        status='EXPLORATORY_FIXED_COHORT_POINT_SENSITIVITY'))
    write_csv(out/'census_gis_rank_sensitivity.csv', output, (
        'panel', 'scenario', 'method', 'project_id', 'cohort_size', 'point_changed',
        'baseline_best', 'baseline_worst', 'alternative_best', 'alternative_worst', 'status'))
