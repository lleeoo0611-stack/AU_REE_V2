"""Package a source-replayed dual-track cycle with fixed-cohort accounting."""
import argparse
import csv
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from au_ree_v2.iteration_review import audit_summary, review_coverage_cycle
from au_ree_v2.store import filehash


def package(before, after, repeat, manifest, snapshots, test_report, out):
    before, after, repeat, snapshots, out = map(Path, (before, after, repeat, snapshots, out))
    out.mkdir(parents=True, exist_ok=True)
    summary = json.loads((after/'summary.json').read_text('utf8'))
    audit = audit_summary(after)
    audit_summary(repeat)
    previous = json.loads((before/'summary.json').read_text('utf8'))
    if summary['database_modified'] or summary['database_sha256'] != previous['database_sha256']:
        raise ValueError('CYCLE_CANONICAL_DATABASE_CHANGED')
    for name, sha in summary['output_hashes'].items():
        if filehash(repeat/name) != sha:
            raise ValueError('CYCLE_REPLAY_HASH_MISMATCH')
    suite = ET.parse(test_report).getroot().find('testsuite')
    if suite is None or any(int(suite.get(key, '0')) for key in ('failures', 'errors')):
        raise ValueError('CYCLE_TESTS_NOT_PASSED')
    ledgers = dict(review_ledger_sha256='asx_source_reviews.json',
                   discovery_ledger_sha256='asx_discovery_reviews.json',
                   identity_ledger_sha256='asx_project_identity_reviews.json')
    for key, name in ledgers.items():
        if filehash(snapshots/name) != summary[key]:
            raise ValueError('CYCLE_SNAPSHOT_LEDGER_MISMATCH:'+name)
    declaration = json.loads(Path(manifest).read_text('utf-8-sig'))
    # Search strings may contain the private external input's company pairing.
    # Publish query fingerprints and derived findings, not original input rows.
    for track in declaration.get('tracks', {}).values():
        for record in track.get('records', []):
            query = str(record['query'])
            record['query'] = 'sha256:'+hashlib.sha256(query.encode('utf8')).hexdigest()
    declaration['validation'] = dict(
        sources=dict(passed=True, evidence='Complete export replay; three source-ledger hashes verified'),
        tests=dict(passed=True, evidence=filehash(test_report)),
        reproducibility=dict(passed=True, evidence='All four CSVs match independent repeated export'))
    review = review_coverage_cycle(before, after, declaration)
    for name in (*summary['output_hashes'], 'summary.json'):
        shutil.copyfile(after/name, out/name)
    for name in ledgers.values():
        shutil.copyfile(snapshots/name, out/name)
    (out/'cycle_review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    (out/'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    with (out/'missing_fields.csv').open(encoding='utf-8-sig', newline='') as handle:
        from collections import Counter
        counts = Counter(row['reason'] for row in csv.DictReader(handle))
    with (out/'remaining_gap_reasons.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle); writer.writerow(['reason', 'blank_cells']); writer.writerows(counts.most_common())
    fingerprints = {p.as_posix():filehash(p) for folder in ('src', 'tools', 'config')
                    for p in sorted(Path(folder).rglob('*')) if p.is_file() and p.suffix in ('.py', '.json')}
    fingerprints.update({'config/'+name:filehash(snapshots/name) for name in ledgers.values()})
    validation = dict(version='source-replayed-coverage-cycle-v1', cycle_id=review['cycle_id'],
        baseline_commit='bc6a90139d58d8ede2bed94321b58f393709edf5',
        current_integrity=audit, database_sha256=summary['database_sha256'], database_modified=False,
        repeated_csv_exports_identical=True, stopping_rule=review['stopping_rule'],
        tests=dict(report_sha256=filehash(test_report),tests_including_subtests=int(suite.get('tests', '0')),
                   failures=0,errors=0,skipped=int(suite.get('skipped','0'))),
        code_fingerprint=fingerprints,
        artifact_hashes={p.name:filehash(p) for p in out.iterdir() if p.is_file() and p.name!='validation.json'},
        limitations='Reviewer search declarations are recorded, not independently proven by the counter; no national completeness or remote CI claim.')
    (out/'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    return review['stopping_rule']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('before', 'after', 'repeat', 'manifest', 'snapshots', 'test-report', 'out'):
        parser.add_argument('--'+key, required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.before,args.after,args.repeat,args.manifest,args.snapshots,args.test_report,args.out), indent=2))
