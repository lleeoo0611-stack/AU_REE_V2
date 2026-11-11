"""Reclassify current blank diagnostics offline without changing table or provenance."""
import argparse
import csv
import json
from pathlib import Path
from au_ree_v2.blank_classification import classify_blanks,load_blank_rules
from au_ree_v2.iteration_review import audit_summary
from au_ree_v2.store import filehash

ROOT=Path(__file__).resolve().parents[1]


def refresh(folder):
    folder=Path(folder)
    def read(name):
        with (folder/name).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);return list(reader),reader.fieldnames
    protected={n:filehash(folder/n) for n in ('專案總表.csv','field_provenance.csv','census_inventory.csv')}
    rows,_=read('專案總表.csv');trace,_=read('field_provenance.csv');gaps,fields=read('missing_fields.csv')
    rules=load_blank_rules(ROOT/'config'/('blank_classification_legacy53.json' if len(rows[0])==53 else 'blank_classification.json'))
    coverage=classify_blanks(rows,gaps,trace,rules)
    # Match the canonical exporter schema; preserve all existing diagnostic columns.
    fields=['project_id','column','reason','blank_class','blank_rule_id']+[c for c in fields if c not in ('project_id','column','reason','blank_class','blank_rule_id')]
    with (folder/'missing_fields.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(gaps)
    summary=json.loads((folder/'summary.json').read_text('utf8'))
    book=json.loads((ROOT/'config/classification_codebook.json').read_text('utf8'))
    summary.update(blank_coverage=coverage,classification_codebook=dict(version=book['version'],status=book['status'],sha256=filehash(ROOT/'config/classification_codebook.json')))
    summary['output_hashes']['missing_fields.csv']=filehash(folder/'missing_fields.csv')
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    audit=audit_summary(folder)
    (folder/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    validation=json.loads((folder/'validation.json').read_text('utf8'))
    validation['engineering_overlay']=dict(only_blank_diagnostics_changed=True,no_new_data_round=True,
        blank_rules_sha256=rules['sha256'],classification_codebook_status=book['status'],
        note='Historical source_replay_commit/stopping_rule/tests refer to round20. Engineering validation recorded separately in results/convergence-codebook.')
    validation['artifact_hashes']={n:filehash(folder/n) for n in validation['artifact_hashes']}
    (folder/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    assert all(filehash(folder/n)==sha for n,sha in protected.items()), 'PROTECTED_OUTPUT_CHANGED'
    return coverage


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--folder',required=True)
    print(json.dumps(refresh(parser.parse_args().folder),ensure_ascii=False,indent=2))
