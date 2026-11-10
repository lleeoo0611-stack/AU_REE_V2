"""Rebuild the reviewed 53-column Census projection twice from local evidence."""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'src'))
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.project_summary import export_summary
from au_ree_v2.project_identity import extend_summary
from au_ree_v2.store import filehash


def asset_sets(value):
    """Include nested archive proofs as well as primary PDF references."""
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('asset_set'), str):
            found.add(value['asset_set'])
        for item in value.values():
            found.update(asset_sets(item))
    elif isinstance(value, list):
        for item in value:
            found.update(asset_sets(item))
    return found


def output_paths(prefix, census_root):
    prefix = Path(prefix).resolve()
    census_root = Path(census_root).resolve()
    paths = {key: prefix.with_name(prefix.name + '-' + key)
             for key in ('a-base52', 'a-53', 'b-base52', 'b-53')}
    paths['receipt'] = prefix.with_name(prefix.name + '-rebuild.json')
    if any(path.is_relative_to(census_root) for path in paths.values()):
        raise ValueError('REBUILD_OUTPUT_MUST_BE_OUTSIDE_CENSUS')
    if any(path.exists() for path in paths.values()):
        raise ValueError('REBUILD_REQUIRE_FRESH_OUTPUT_PREFIX')
    return paths


def load_assets(path, census_root, ledgers):
    cfg = json.loads(Path(path).read_text(encoding='utf8'))
    if cfg.get('version') != 'asx-local-assets-v1':
        raise ValueError('REBUILD_ASSET_MAP_VERSION')
    roots = {key: (REPO / value).resolve() for key, value in cfg['roots'].items()}
    roots['canonical'] = Path(census_root).resolve()
    required = set().union(*(asset_sets(ledger) for ledger in ledgers))
    missing = sorted(key for key in required if key not in roots or not roots[key].is_dir())
    if missing:
        raise ValueError('REBUILD_LOCAL_ASSETS_MISSING:' + ','.join(missing))
    return roots


def review_cutoff(ledgers, requested=None):
    # The source-review v2 ledger has no top-level cutoff. Discovery and
    # identity ledgers carry the frozen research cutoff; acquisition dates
    # cannot substitute for it.
    declared = {ledger['cutoff'] for ledger in ledgers if ledger.get('cutoff')}
    if len(declared) != 1 or (requested is not None and requested not in declared):
        raise ValueError('REBUILD_LEDGER_CUTOFF_MISMATCH')
    return next(iter(declared))


def rebuild(census_root, database, run_dir, out_prefix, asset_map, cutoff=None):
    census_root, database = Path(census_root).resolve(), Path(database).resolve()
    paths = output_paths(out_prefix, census_root)
    ledger_paths = [REPO / 'config' / name for name in (
        'asx_source_reviews.json', 'asx_discovery_reviews.json', 'asx_project_identity_reviews.json')]
    location_ledger=REPO/'config/asx_location_reviews.json'
    if location_ledger.exists():ledger_paths.append(location_ledger)
    ledgers = [json.loads(p.read_text(encoding='utf8')) for p in ledger_paths]
    cutoff = review_cutoff(ledgers, cutoff)
    assets = load_assets(asset_map, census_root, ledgers)
    before = filehash(database)
    projection_configs={p.name:filehash(p) for p in (REPO/'config/classification_codebook.json',REPO/'config/blank_classification.json') if p.exists()}
    audits = []
    for pass_name in ('a', 'b'):
        print('Rebuilding independently: ' + pass_name, flush=True)
        export_summary(census_root, database, run_dir, paths[pass_name + '-base52'],
                       cutoff=cutoff, review_ledger=ledger_paths[0],
                       asset_roots=assets, discovery_ledger=ledger_paths[1],
                       location_ledger=location_ledger if location_ledger.exists() else None)
        extend_summary(paths[pass_name + '-base52'], paths[pass_name + '-53'], ledger_paths[2], assets)
        audits.append(audit_summary(paths[pass_name + '-53']))
        if filehash(database) != before:
            raise ValueError('REBUILD_CENSUS_DATABASE_CHANGED')
    if audits[0]['output_hashes'] != audits[1]['output_hashes']:
        raise ValueError('REBUILD_INDEPENDENT_OUTPUT_MISMATCH')
    if any(filehash(REPO/'config'/name)!=value for name,value in projection_configs.items()):
        raise ValueError('REBUILD_PROJECTION_CONFIGURATION_CHANGED')
    receipt = dict(version='reviewed-asx-census-rebuild-v1', cutoff=cutoff,
                   database_sha256=before, database_modified=False,
                   ledger_sha256={p.name: filehash(p) for p in ledger_paths},
                   asset_map_sha256=filehash(asset_map), independent_rebuilds=2,projection_configuration_sha256=projection_configs,
                   output_hashes=audits[0]['output_hashes'], audit=audits[0],
                   limitation='REPLAY_OF_APPROVED_EVIDENCE;NOT_A_FRESH_SEARCH_OR_FULL_SCOPE_STOP_DECISION')
    paths['receipt'].write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(projects=audits[0]['projects'], columns=audits[0]['columns'],
                          filled_cells=audits[0]['filled_cells'], blank_cells=audits[0]['remaining_blank_cells'],
                          independent_outputs_identical=True, database_modified=False,
                          table=str(paths['a-53'] / '專案總表.csv'), receipt=str(paths['receipt'])),
                     ensure_ascii=False, indent=2))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--census-root', type=Path, default=REPO.parent / 'AU_REE_V2')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--run-dir', type=Path)
    parser.add_argument('--out-prefix', type=Path, required=True)
    parser.add_argument('--asset-map', type=Path, default=REPO / 'config/asx_local_asset_roots.json')
    parser.add_argument('--as-of', help='Must match the frozen discovery/identity ledger cutoff')
    args = parser.parse_args()
    database = args.database or args.census_root / 'work/phase22/verified-performance-v3/isolated-round-0/after/canonical.sqlite'
    run_dir = args.run_dir or args.census_root / 'results/phase22-2026-11-06'
    rebuild(args.census_root, database, run_dir, args.out_prefix, args.asset_map, args.as_of)


if __name__ == '__main__':
    main()
