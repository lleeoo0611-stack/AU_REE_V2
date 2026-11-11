"""Fail-closed coverage acceptance. Never changes source evidence or publishes."""
import csv
import json
from pathlib import Path
from .store import filehash

FILES = ('專案總表.csv', 'field_provenance.csv', 'missing_fields.csv',
         'census_inventory.csv', 'summary.json', 'audit.json')
DERIVED = frozenset(('已公布元素數_共15項', '已公布元素總和_kt', '元素總和/TREO',
                     '元素數據一致性檢查'))


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def compare_projections(before, after, allow_derived=False):
    before, after = Path(before), Path(after)
    old, new = (read_csv(p/'專案總表.csv') for p in (before, after))
    if not old or not new or list(old[0]) != list(new[0]):
        raise ValueError('COVERAGE_SCHEMA_CHANGED')
    oldrows = {r['專案ID']:r for r in old}
    newrows = {r['專案ID']:r for r in new}
    if len(oldrows) != len(old) or len(newrows) != len(new) or oldrows.keys() != newrows.keys():
        raise ValueError('COVERAGE_COHORT_CHANGED')
    trace = [{(p['project_id'],p['column']):p for p in read_csv(folder/'field_provenance.csv')}
             for folder in (before,after)]
    additions, changes = [], []
    for pid,row in oldrows.items():
        for column,value in row.items():
            updated = newrows[pid][column]
            key = pid,column
            if value != updated:
                item = dict(project_id=pid,project=row['專案名稱'],column=column,
                            old_value=value,new_value=updated)
                if value:
                    if not allow_derived or column not in DERIVED or not updated:
                        raise ValueError('COVERAGE_EXISTING_VALUE_CHANGED:'+str(key))
                    changes.append(item)
                else:
                    additions.append(item)
            elif value and trace[0].get(key) != trace[1].get(key):
                raise ValueError('COVERAGE_EXISTING_PROVENANCE_CHANGED:'+str(key))
    causal_projects={a['project_id'] for a in additions if '_氧化' in a['column'] or a['column']=='NdPr蘊藏量_kt_需兩者皆公布'}
    if any(c['project_id'] not in causal_projects for c in changes):
        raise ValueError('COVERAGE_DERIVED_CHANGE_WITHOUT_NEW_SOURCE_VALUE')
    if filehash(before/'census_inventory.csv') != filehash(after/'census_inventory.csv'):
        raise ValueError('COVERAGE_INVENTORY_CHANGED')
    return additions,changes


def identical_replays(a,b):
    hashes = {}
    for name in FILES:
        first,second = filehash(Path(a)/name),filehash(Path(b)/name)
        if first != second:
            raise ValueError('COVERAGE_REBUILD_MISMATCH:'+name)
        hashes[name] = first
    return hashes


def verify_protected(repo, baseline):
    repo = Path(repo)
    baseline = json.loads(Path(baseline).read_text('utf8'))
    for name,expected in baseline['protected'].items():
        if filehash(repo/name) != expected:
            raise ValueError('COVERAGE_PROTECTED_CHANGED:'+name)
    if filehash(Path(baseline['census_path'])) != baseline['census_sha256']:
        raise ValueError('COVERAGE_CENSUS_CHANGED')
    return dict(protected_files=len(baseline['protected']),census_sha256=baseline['census_sha256'])


def coverage(folder):
    rows = read_csv(Path(folder)/'專案總表.csv')
    filled = sum(v != '' for row in rows for v in row.values())
    resource = [r for r in rows if r['總TREO蘊藏量_kt'] != '']
    summary = json.loads((Path(folder)/'summary.json').read_text('utf8'))
    return dict(rows=len(rows),columns=len(rows[0]),filled=filled,blank=len(rows)*len(rows[0])-filled,
                all_denominator=len(rows)*len(rows[0]),all_coverage=filled/(len(rows)*len(rows[0])),
                treo_rows=len(resource),treo_filled=sum(v!='' for r in resource for v in r.values()),
                treo_denominator=len(resource)*len(rows[0]),existing_exclusion_policy=summary.get('blank_coverage'))
