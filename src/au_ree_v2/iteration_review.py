"""Audit a current summary without equating download counts with scientific coverage."""
import csv
import json
from pathlib import Path
from .store import filehash

# Frozen 52-column contract: 10 resource/production and 15 oxide columns.
SCIENCE_INDEXES = tuple(range(15,25)) + tuple(range(37,52))

def audit_summary(folder):
    folder=Path(folder)
    def read(name):
        with (folder/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
    rows=read('專案總表.csv')
    columns=json.loads((Path(__file__).resolve().parents[2]/'config/project_summary_columns.json').read_text('utf8'))
    if not rows or list(rows[0])!=columns:raise ValueError('ITERATION_SUMMARY_CONTRACT_MISMATCH')
    keys=[r['專案ID'] for r in rows]
    if len(set(keys))!=len(keys):raise ValueError('ITERATION_DUPLICATE_PROJECT')
    provenance=read('field_provenance.csv'); missing=read('missing_fields.csv')
    trace={(r['project_id'],r['column']):r for r in provenance}
    gaps={(r['project_id'],r['column']):r for r in missing}
    if len(trace)!=len(provenance) or len(gaps)!=len(missing):raise ValueError('ITERATION_DUPLICATE_CELL_RECORD')
    filled={(r['專案ID'],c):v for r in rows for c,v in r.items() if v!=''}
    blanks={(r['專案ID'],c) for r in rows for c,v in r.items() if v==''}
    if set(trace)!=set(filled) or any(trace[k]['value']!=v for k,v in filled.items()):raise ValueError('ITERATION_PROVENANCE_CELL_MISMATCH')
    if set(gaps)!=blanks:raise ValueError('ITERATION_MISSING_DIAGNOSTIC_MISMATCH')
    summary=json.loads((folder/'summary.json').read_text('utf8'))
    for name,sha in summary['output_hashes'].items():
        if filehash(folder/name)!=sha:raise ValueError('ITERATION_OUTPUT_HASH_MISMATCH')
    scientific=[columns[i] for i in SCIENCE_INDEXES]
    return dict(projects=len(rows),columns=len(columns),filled_cells=len(filled),total_cells=len(rows)*len(columns),
                remaining_blank_cells=len(blanks),scientific_columns=scientific,
                scientific_filled_cells=sum(r[c]!='' for r in rows for c in scientific),
                scientific_total_cells=len(rows)*len(scientific),output_hashes=summary['output_hashes'],
                provenance_complete=True,missing_diagnostics_complete=True)
