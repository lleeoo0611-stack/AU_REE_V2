"""Config-driven blank semantics; the data cells and their provenance stay intact."""
import json
from collections import Counter
from pathlib import Path
from .store import filehash

CLASSES={'UNKNOWN','NOT_APPLICABLE_STAGE','NO_COMPARATOR_SOURCE','PENDING_CODEBOOK','NOT_APPLICABLE_NO_MRE'}


def load_blank_rules(path):
    cfg=json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if cfg.get('default_class')!='UNKNOWN' or not isinstance(cfg.get('rules'),list):
        raise ValueError('BLANK_CONFIG_INVALID')
    excluded=cfg.get('excluded_from_adjusted_denominator')
    if not isinstance(excluded,list) or not set(excluded)<={'NOT_APPLICABLE_STAGE','NO_COMPARATOR_SOURCE','NOT_APPLICABLE_NO_MRE'}:
        raise ValueError('BLANK_EXCLUDED_CLASSES_INVALID')
    ids=[]
    for rule in cfg['rules']:
        ids.append(rule['id']);when=rule.get('when',{})
        if (rule.get('blank_class') not in CLASSES or not rule.get('columns')
            or not when or set(when)-{'reason_in','field_values_in','empty_fields','require_source_provenance_for','no_selected_mre'}):
            raise ValueError('BLANK_RULE_INVALID')
    if len(set(ids))!=len(ids):raise ValueError('BLANK_DUPLICATE_RULE')
    return dict(config=cfg,sha256=filehash(path))


def classify_blanks(rows,diagnostics,provenance,rules):
    by_id={r['專案ID']:r for r in rows}
    trace={(p['project_id'],p['column']):p for p in provenance}
    for gap in diagnostics:
        row=by_id[gap['project_id']]
        if row[gap['column']]!='':raise ValueError('BLANK_RULE_TARGET_IS_FILLED')
        label='UNKNOWN';rule_id='default-unknown'
        for rule in rules['config']['rules']:
            if gap['column'] not in rule['columns']:continue
            when=rule['when']
            if when.get('no_selected_mre'):
                from .stage_rules import selected_mre
                if selected_mre(row,provenance)[0] is not False:continue
            if 'reason_in' in when and gap.get('reason') not in when['reason_in']:continue
            if any(row.get(field) not in values for field,values in when.get('field_values_in',{}).items()):continue
            if any(row.get(field)!='' for field in when.get('empty_fields',[])):continue
            if any(not trace.get((gap['project_id'],field),{}).get('source_sha256')
                   or trace[(gap['project_id'],field)].get('value')!=row.get(field)
                   for field in when.get('require_source_provenance_for',[])):continue
            label=rule['blank_class'];rule_id=rule['id'];break
        gap.update(blank_class=label,blank_rule_id=rule_id)
    return blank_coverage(rows,diagnostics,rules)


def blank_coverage(rows,diagnostics,rules):
    counts=Counter(g['blank_class'] for g in diagnostics)
    labels=CLASSES if rules['config'].get('version')=='round3-v1' else CLASSES-{'NOT_APPLICABLE_NO_MRE'}
    total=sum(len(r) for r in rows);filled=sum(v!='' for r in rows for v in r.values())
    excluded=sum(counts[c] for c in rules['config']['excluded_from_adjusted_denominator'])
    return dict(total_cells=total,filled_cells=filled,blank_cells=total-filled,
        blank_class_counts={c:counts[c] for c in sorted(labels)},excluded_structural_blanks=excluded,
        adjusted_denominator=total-excluded,raw_coverage=filled/total if total else None,
        adjusted_coverage=filled/(total-excluded) if total>excluded else None,
        excluded_classes=rules['config']['excluded_from_adjusted_denominator'],
        rules_version=rules['config']['version'],rules_sha256=rules['sha256'],
        limitation='ADJUSTED_INFORMATION_COVERAGE_CONVENTION_NOT_CURRENT_STATUS_OR_PROOF_OF_ABSENCE')
