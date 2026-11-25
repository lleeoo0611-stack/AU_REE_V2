"""Shared Census rules for evidence binding, interpretation and source text."""

import json
import re
from pathlib import Path


def summary_matching_resource_pdf(observation, raw, bundle):
    """Allow page-verified composition from an explicitly matched PDF edition."""
    reference = raw.get('census_equivalent_resource_pdf')
    if not reference or bundle.get('partial_resource_projection'):
        return False
    ore = next(o for o in bundle['observations'] if o['variable']=='ore_mt')
    return (
        observation['source_sha'] != bundle['source_sha256']
        and bool(raw.get('page_extraction_sha256'))
        and reference == dict(source_sha256=bundle['source_sha256'], **bundle['value'])
        and all(observation[k] == bundle[k] for k in ('statement_id','scope','effective_date'))
        and observation['category'] == ore['category']
    )


def summary_settings(root):
    book=json.loads((Path(root)/'config/summary_rules.json').read_text(encoding='utf8'))
    if any(not p.get('source_file') or not p.get('source_key') for p in book['parameters'].values()):
        raise ValueError('SUMMARY_RULE_ORIGIN_REQUIRED')
    rules={k:v['value'] for k,v in book['parameters'].items()}
    decisions=json.loads((Path(root)/'config/researcher_rule_decisions.json').read_text(encoding='utf8'))['decisions']
    return rules,[d for d in decisions if isinstance(d.get('decided_by'),str) and d['decided_by'].strip()]


def summary_decision(decisions, rule, project_id=None, bundle=None):
    matches=[d for d in decisions if d.get('rule')==rule and (project_id is None or d.get('project_id')==project_id)]
    if bundle is not None:
        matches=[d for d in matches if isinstance(d.get('scope'),dict) and
            d['scope'].get('statement_id')==bundle['statement_id'] and d['scope'].get('source_sha256')==bundle['source_sha256']]
    if len(matches)>1:raise ValueError('SUMMARY_AMBIGUOUS_RULE_DECISION:'+rule)
    return matches[0] if matches else None


def summary_norm(text):
    return re.sub(r'\s+',' ',str(text)).strip().casefold()


def summary_region_text(page, rect):
    words=[w for w in page.get_text('words',sort=True)
           if rect.x0<=(w[0]+w[2])/2<=rect.x1 and rect.y0<=(w[1]+w[3])/2<=rect.y1]
    return ' '.join(w[4] for w in words)


def summary_observation(observation):
    raw=json.loads(observation['raw']);reviewed=raw.get('raw',{}).get('reviewed_observation',{})
    result=dict(reviewed,**raw);result['review_contract']=raw.get('raw',{}).get('review_contract',{})
    return result
