"""Assess the six formal research gates against versioned decisions and selected originals."""
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from .selection_rules import date_end
from .store import canonical, digest, filehash
from .tabular import read_csv, write_csv


# Separate attestations, bound to located evidence. Study completion alone cannot attest pre-FID.
REQUIRED = {
    'ID': ('project_identity', 'project_footprint'),
    'ROLE': ('planned_ree_product_role',),
    'WINDOW': ('published_economic_study', 'australian_project', 'active_at_cutoff', 'pre_fid_at_cutoff'),
    'JORC': ('mineral_resource', 'jorc_edition', 'classification', 'tonnage', 'grade', 'cutoff_grade', 'reo_basis'),
    'GIS_RELEASE': ('representative_geometry', 'official_road_layer', 'official_rail_layer',
                    'official_power_layer', 'official_port_layer', 'distance_qa'),
}
ASSERTION_GATE = {assertion: gate for gate, assertions in REQUIRED.items() for assertion in assertions}
# These authoritative observation variables express the specific predicate directly.
# An arbitrary field from the same Project/document never becomes a different predicate.
def supports_assertion(assertion, fact):
    variable = fact.get('variable')
    if fact.get('gate') != ASSERTION_GATE[assertion]:
        return False
    if variable == 'ore_mt' and assertion == 'tonnage':
        return fact.get('unit') == 'Mt' and isinstance(fact.get('value'), (int,float)) and fact['value'] > 0
    if variable == 'grade' and assertion == 'grade':
        return (fact.get('unit') in ('ppm','%','pct') and fact.get('basis') in ('TREO','REO_SCOPED_BREAKDOWN')
                and isinstance(fact.get('value'), (int,float)) and fact['value'] >= 0)
    # Typed, affirmative observations can be verified by the same canonical claim workflow.
    return variable == assertion and fact.get('value') == 1


METADATA = {
    'ID': ('verified_project_id', 'project_identity_scope', 'project_footprint_ref'),
    'ROLE': ('ree_product_role_ref',),
    'WINDOW': ('approved_study_document_id', 'study_published_asof'),
    'JORC': ('resource_statement_id', 'resource_basis', 'original_jorc_ref'),
    'PANEL': ('approved_panel_version',),
    'GIS_RELEASE': ('approved_gis_evidence_id',),
}
FIELD_GATE = {
    '專案名稱': 'ID', '產品/產出': 'ROLE', '開發階段': 'WINDOW',
    '礦石蘊藏量_Mt': 'JORC', '緯度': 'GIS_RELEASE', '經度': 'GIS_RELEASE',
}


def day_in_window(value, cutoff):
    try:
        return bool(value) and date.fromisoformat(date_end(value)) <= date.fromisoformat(cutoff)
    except (ValueError, TypeError):
        return False


def contracts(root):
    compat_path = root/'config/eligibility_compatibility.json'
    config = json.loads(compat_path.read_text(encoding='utf8'))
    paths = {}
    for name, declared in config['imports'].items():
        path = root/declared['path']
        if filehash(path) != declared['sha256']:
            raise ValueError(f'UPSTREAM_POLICY_SHA_MISMATCH: {name}')
        paths[name] = path
    policy = json.loads(paths['policy'].read_text(encoding='utf8'))
    review_path = root/'config/formal_c1_review.json'
    review = json.loads(review_path.read_text(encoding='utf8'))
    if review['policy_id'] != policy['policy_id'] or config['upstream_policy'] != policy:
        raise ValueError('C1_REVIEW_POLICY_MISMATCH')
    if set(policy['C1_required_gates']) != set(METADATA) or len(policy['C1_required_gates']) != len(METADATA):
        raise ValueError('UNSUPPORTED_FORMAL_GATE_CONTRACT')
    criteria = json.loads(paths['criteria'].read_text(encoding='utf8'))
    return dict(policy=policy, review=review, criteria={c['code']: c for c in criteria['criteria']},
                criteria_version=criteria['version'], crosswalk=config['approved_crosswalk'],
                signatures=read_csv(paths['gates']), metadata=read_csv(paths['identity']),
                hashes={**{k: v['sha256'] for k, v in config['imports'].items()},
                        'crosswalk': digest(config['approved_crosswalk']), 'review': filehash(review_path)})


def source_date(source):
    if source.get('publication_date'):
        return source['publication_date']
    # A historical GIS version may instead have a proven public availability date.
    if source.get('kind') not in ('pdf', 'html', 'document_extraction', 'pdf_page_extraction'):
        return source.get('available_date')
    return None


def evidence_inventory(row, trace, observations, sources, criteria):
    """Collect located, project-bound facts; derived summary codes do not certify an individual gate."""
    pid = row['專案ID']
    facts = {}
    formal_variables = {v['variable']: k for k, v in criteria.items()}
    for o in observations.get(pid, ()):
        sha = o['source_sha']
        if sha not in sources or not o['locator'] or o['value'] is None or o['status'] != 'AUTO_VALIDATED':
            continue
        code = formal_variables.get(o['variable'])
        gate = {'D1':'WINDOW', 'R1':'JORC', 'S1':'JORC'}.get(code)
        if o['variable'] in ('ore_mt', 'grade') or o['variable'].startswith('reported_resource_'):
            gate = 'JORC'
        gate = ASSERTION_GATE.get(o['variable'], gate)
        raw = json.loads(o['raw'])
        facts[o['obs_id']] = dict(
            project_id=pid, scope=o['scope'], source_sha=sha, effective_date=o['effective_date'],
            date=source_date(sources[sha]), acquired_at=sources[sha].get('acquired_at'),
            source_key=sources[sha]['key'], source_url=sources[sha].get('url'), locator=o['locator'],
            variable=o['variable'], candidate_code=code, gate=gate, value=o['value'],
            basis=o['basis'], unit=o['unit'], statement=o.get('statement_id'),
            material_basis=raw.get('material_basis'),
        )
    for col, gate in FIELD_GATE.items():
        r = trace.get((pid, col))
        if not r or not r['value'] or not r['locator']:
            continue
        shas = r['source_sha256'].split(';')
        # Composite traces cannot be dated using one arbitrary contributor.
        if len(shas) != 1 or shas[0] not in sources:
            continue
        sha = shas[0]
        ref = 'field:' + digest([pid, col, r['locator'], sha, r['value']])
        facts[ref] = dict(project_id=pid, scope=r['scope'], source_sha=sha, date=source_date(sources[sha]),
                          effective_date=r.get('effective_date'), locator=r['locator'], value=r['value'],
                          acquired_at=sources[sha].get('acquired_at'), source_key=sources[sha]['key'],
                          source_url=sources[sha].get('url'), gate=gate, candidate_code=None,
                          variable=col, statement=None)
    return facts


def visible(fact, cutoff):
    return day_in_window(fact['date'], cutoff) and day_in_window(fact['effective_date'], cutoff)


def valid_review(row, cutoff, review_asof):
    if not row or not all(str(row.get(k) or '').strip() for k in ('reviewer_id', 'reviewed_at', 'approval_ref')):
        return False
    try:
        return date.fromisoformat(cutoff) <= date.fromisoformat(row['reviewed_at']) <= date.fromisoformat(review_asof)
    except (TypeError, ValueError):
        return False


def fixed_panel(inputs):
    review, policy = inputs['review'], inputs['policy']
    panel = review.get('fixed_panel_decision') or {}
    keys = review['candidate_panels'].get(panel.get('candidate_id'))
    if (not keys or panel.get('policy_id') != policy['policy_id'] or not panel.get('version')
            or panel.get('criteria_version') != inputs['criteria_version']
            or panel.get('status') != 'APPROVED_BEFORE_RANKING' or panel.get('source_asof') != policy['source_asof']
            or not valid_review(panel, policy['source_asof'], review['review_asof'])):
        return None
    if len({inputs['criteria'][code]['domain'] for code in keys}) != 6:
        return None
    return panel


def signed_status(rows, facts, cutoff, review_asof):
    if not rows:
        return 'UNSIGNED'
    if len(rows) != 1:
        return 'CONFLICTING_SIGNATURES'
    decision = rows[0]
    if (decision['source_asof'] != cutoff or not valid_review(decision, cutoff, review_asof)
            or not all(decision.get(k) for k in ('document_id', 'original_sha256_or_html_ref', 'reason_code'))
            or decision['decision_status'] not in ('PASS', 'HOLD', 'EXCLUDE')):
        return 'INVALID_SIGNATURE'
    if not any(decision['document_id'] in (f['source_key'], f['source_sha'])
               and decision['original_sha256_or_html_ref'] in (f['source_sha'], f.get('source_url'))
               for f in facts.values()):
        return 'SIGNED_SOURCE_NOT_VERIFIED'
    return decision['decision_status']


def check_attestation(gate, refs, facts, meta, inputs, panel, signing):
    policy, review = inputs['policy'], inputs['review']
    cutoff = policy['source_asof']
    if not refs:
        return 'MISSING_GATE_BINDING'
    if len(refs) != 1:
        return 'CONFLICTING_GATE_BINDINGS'
    ref = refs[0]
    if ref.get('source_asof') != cutoff or ref.get('policy_id') != policy['policy_id']:
        return 'POLICY_OR_CUTOFF_MISMATCH'
    if (not meta or any(not meta.get(k) for k in METADATA[gate])
            or not meta.get('project_identity_scope') or ref.get('scope') != meta['project_identity_scope']):
        return 'MISSING_OR_MISMATCHED_PROJECT_SCOPE'
    if gate == 'PANEL' and (not panel or meta['approved_panel_version'] != panel['version']):
        return 'NO_MATCHING_FIXED_PANEL'
    required = review['candidate_panels'][panel['candidate_id']] if gate == 'PANEL' else REQUIRED[gate]
    assertions = ref.get('evidence') or {}
    if not all(assertions.get(key) in facts for key in required):
        return 'MISSING_LOCATED_GATE_EVIDENCE'
    if len({assertions[key] for key in required}) != len(required):
        return 'REUSED_ASSERTION_EVIDENCE'
    bound = [facts[assertions[key]] for key in required]
    if any(f['project_id'] != ref['project_id'] or f['scope'] != ref['scope'] for f in bound):
        return 'EVIDENCE_SCOPE_MISMATCH'
    if not all(visible(f, cutoff) for f in bound):
        return 'EVIDENCE_OUTSIDE_POLICY_WINDOW'
    if gate != 'PANEL' and any(not supports_assertion(key, fact) for key, fact in zip(required, bound)):
        return 'ASSERTION_EVIDENCE_TYPE_MISMATCH'
    if gate in ('WINDOW','GIS_RELEASE') and len({(f['source_sha'],f['locator']) for f in bound}) != len(bound):
        return 'ASSERTION_LOCATORS_UNRESOLVED'
    if gate == 'PANEL':
        for code, fact in zip(required, bound):
            crit = inputs['criteria'][code]
            if (fact.get('candidate_code') != code or fact.get('unit') != crit['unit']
                    or fact.get('basis') != crit['basis']):
                return 'CRITERION_VARIABLE_UNIT_OR_BASIS_MISMATCH'
    if gate == 'WINDOW':
        state = ref.get('window') or {}
        if (state.get('asof') != cutoff or state.get('country') != 'AU'
                or state.get('activity') != 'ACTIVE' or state.get('investment_status') != 'PRE_FID'
                or state.get('study_status') != 'PUBLISHED_COMPLETED'
                or state.get('study_level') not in ('SCOPING','PFS','FS','DFS','BFS')):
            return 'NO_EXPLICIT_ACTIVE_PRE_FID_ECONOMIC_STUDY_WINDOW'
        if not day_in_window(meta['study_published_asof'], cutoff):
            return 'STUDY_OUTSIDE_POLICY_WINDOW'
        study = facts[assertions['published_economic_study']]
        if (meta['approved_study_document_id'] not in (study['source_key'], study['source_sha'])
                or meta['study_published_asof'] != study['date']):
            return 'STUDY_DOCUMENT_OR_DATE_MISMATCH'
    if gate == 'JORC':
        if meta['resource_basis'] not in policy['JORC_allowed_REO_basis']:
            return 'INCOMPATIBLE_RESOURCE_BASIS'
        if any(f.get('statement') != meta['resource_statement_id'] for f in bound):
            return 'RESOURCE_STATEMENT_MISMATCH'
    if gate == 'ROLE' and ref.get('product_role') not in ('PRIMARY_REE', 'CO_PRODUCT_REE', 'PLANNED_RECOVERED_BYPRODUCT_REE'):
        return 'REE_RECOVERY_ROLE_NOT_CONFIRMED'
    # Match the upstream metadata to the same located original reviewed for this gate.
    ref_key = {'ID': ('project_footprint_ref','project_footprint'), 'ROLE': ('ree_product_role_ref','planned_ree_product_role'),
               'JORC': ('original_jorc_ref','mineral_resource'), 'GIS_RELEASE': ('approved_gis_evidence_id','distance_qa')}.get(gate)
    if ref_key:
        meta_key, assertion = ref_key
        evidence_id = assertions[assertion]
        fact = facts[evidence_id]
        if meta[meta_key] not in (evidence_id, fact['source_key'], fact['source_sha'], fact.get('source_url')):
            return 'UPSTREAM_METADATA_REFERENCE_MISMATCH'
    if not signing:
        return 'LOCATED_EVIDENCE_UNSIGNED'
    if (not ref.get('approval_ref') or ref['approval_ref'] != signing['approval_ref']
            or not any(signing['document_id'] in (f['source_key'], f['source_sha']) and
                       signing['original_sha256_or_html_ref'] in (f['source_sha'], f.get('source_url')) for f in bound)):
        return 'DECISION_EVIDENCE_MISMATCH'
    return 'BOUND_EVIDENCE_VERIFIED'


def assess_project(pid, facts, inputs, census_cutoff, panel):
    policy, review = inputs['policy'], inputs['review']
    cutoff = policy['source_asof']
    links = [r for r in inputs['crosswalk'] if r.get('v2_project_id') == pid]
    group = links[0].get('upstream_review_group_id') if len(links) == 1 else None
    link = links[0] if group else {}
    assigned = [r for r in inputs['crosswalk'] if r.get('upstream_review_group_id') == group
                or (link.get('verified_project_id') and r.get('verified_project_id') == link['verified_project_id'])]
    group_metadata = [r for r in inputs['metadata'] if r.get('review_group_id') == group]
    linked = (bool(group) and len(assigned) == 1 and bool(link.get('approval_ref'))
              and link.get('native_id_evidence') in facts and visible(facts[link['native_id_evidence']], cutoff)
              and supports_assertion('project_identity', facts[link['native_id_evidence']]))
    meta = group_metadata[0] if linked and len(group_metadata) == 1 else {}
    if meta and (not link.get('verified_project_id') or meta.get('verified_project_id') != link['verified_project_id']):
        linked = False
        meta = {}
    rows = []
    for gate in policy['C1_required_gates']:
        leads = {i:f for i,f in facts.items() if f['gate'] == gate or (gate == 'PANEL' and f.get('candidate_code'))}
        eligible = sorted(i for i, f in leads.items() if visible(f, cutoff))
        census_only = sorted(i for i, f in leads.items() if visible(f, census_cutoff) and i not in eligible)
        signs = [r for r in inputs['signatures'] if linked and r['review_group_id'] == group and r['cohort'] == 'C1'
                 and r['gate_id'] == gate]
        signed = signed_status(signs, {i:f for i,f in facts.items() if visible(f,cutoff)}, cutoff, review['review_asof'])
        bindings = [r for r in review['gate_evidence_bindings'] if r['project_id'] == pid and r['gate'] == gate]
        signing = signs[0] if len(signs) == 1 else None
        objective = check_attestation(gate, bindings, facts, meta, inputs, panel, signing)
        if gate == 'PANEL' and not panel:
            objective = 'FORMAL_PANEL_UNSELECTED'
        verified = objective == 'BOUND_EVIDENCE_VERIFIED'
        decision_facts = [leads[i] for i in eligible]
        signed_scope = (bool(meta.get('project_identity_scope')) and signing and
                        any(f['scope'] == meta['project_identity_scope'] and
                            signing['document_id'] in (f['source_key'], f['source_sha']) and
                            signing['original_sha256_or_html_ref'] in (f['source_sha'], f.get('source_url'))
                            for f in decision_facts))
        status = ('PASS' if linked and signed == 'PASS' and verified else
                  signed if linked and signed in ('EXCLUDE','HOLD') and signed_scope else 'PENDING')
        rows.append(dict(project_id=pid, gate=gate, status=status, objective=objective,
                         source_facts='PARTIAL_SOURCE_FACTS' if eligible else 'NO_LOCATED_FACTS',
                         signoff=signed, crosswalk='APPROVED' if linked else 'MISSING_OR_AMBIGUOUS',
                         group_id=group if linked else None, policy_id=policy['policy_id'], source_asof=cutoff,
                         census_cutoff=census_cutoff, formal_source_candidates=len(eligible),
                         census_only_candidates=len(census_only), missing_dates=sum(not f['date'] or not f['effective_date'] for f in leads.values()),
                         evidence=canonical([{k:leads[i].get(k) for k in ('source_sha','source_key','date','effective_date',
                             'acquired_at','locator','variable','scope')} | {'evidence_id': i} for i in eligible]),
                         census_only_evidence_ids=canonical(census_only), approval_ref=(signing or {}).get('approval_ref'),
                         bindings=canonical(bindings)))
    return rows


def release_result(inputs, gate_rows, panel):
    statuses = defaultdict(dict)
    for row in gate_rows:
        statuses[row['project_id']][row['gate']] = row['status']
    required = set(inputs['policy']['C1_required_gates'])
    admitted = sorted(p for p,g in statuses.items() if set(g) == required and all(s == 'PASS' for s in g.values()))
    review = inputs['review']
    qa = review.get('release_qa') or {}
    # A QA approval applies only to these source-bound decisions and this exact panel.
    decision_hash = digest([inputs['policy']['policy_id'], inputs['policy']['source_asof'], panel, gate_rows])
    qa_pass = (bool(admitted) and panel is not None and qa.get('status') == 'PASS'
               and qa.get('decision_set_sha256') == decision_hash
               and valid_review(qa, inputs['policy']['source_asof'], review['review_asof']))
    return dict(gates_checked=len(gate_rows), projects_checked=len(statuses),
                signed_pass_gates=sum(r['status']=='PASS' for r in gate_rows),
                projects_with_all_gates=len(admitted), signed_eligible_projects=admitted,
                decision_set_sha256=decision_hash, release_qa='PASS' if qa_pass else 'PENDING_OR_FAILED',
                release_status='RELEASABLE' if qa_pass else 'NOT_RELEASED',
                formally_releasable=admitted if qa_pass else [])


def write_formal_cohort(root, out, rows, trace, sources, observations, cutoff):
    inputs = contracts(Path(root))
    review, policy = inputs['review'], inputs['policy']
    panel = fixed_panel(inputs)
    gates, panels = [], []
    for row in sorted(rows, key=lambda x:x['專案ID']):
        pid = row['專案ID']
        facts = evidence_inventory(row, trace, observations, sources, inputs['criteria'])
        gates.extend(assess_project(pid, facts, inputs, cutoff, panel))
        formal_facts = [f for f in facts.values() if visible(f, policy['source_asof'])]
        located = {f['candidate_code'] for f in formal_facts if f.get('candidate_code')}
        compatible = {f['candidate_code'] for f in formal_facts if f.get('candidate_code') and
                      f['unit'] == inputs['criteria'][f['candidate_code']]['unit'] and
                      f['basis'] == inputs['criteria'][f['candidate_code']]['basis']}
        for name, codes in review['candidate_panels'].items():
            panels.append(dict(project_id=pid, state=row.get('州省地區'), stage=row.get('開發階段代碼'),
                               deposit_type=row.get('礦床型態'), panel=name, criteria=' '.join(codes),
                               located_variables=' '.join(c for c in codes if c in located),
                               compatible_variables=' '.join(c for c in codes if c in compatible),
                               missing_compatible=' '.join(c for c in codes if c not in compatible),
                               all_variables_located=int(set(codes)<=located), all_exact_basis=int(set(codes)<=compatible),
                               source_asof=policy['source_asof'], criteria_version=inputs['criteria_version']))
    receipt = release_result(inputs, gates, panel)
    receipt.update(policy_id=policy['policy_id'], source_asof=policy['source_asof'], census_cutoff=cutoff,
                   review_asof=review['review_asof'], imported_panel_status=policy['C1_criteria_panel_status'],
                   fixed_panel_version=panel['version'] if panel else None, crosswalk_version=review['crosswalk_version'],
                   approved_crosswalk_entries=len(inputs['crosswalk']), imported_signatures=len(inputs['signatures']),
                   criteria_version=inputs['criteria_version'], input_hashes=inputs['hashes'],
                   protocol=review['panel_protocol'], evaluator=review['version'],
                   panel_coverage={name:dict(projects=sum(p['panel']==name for p in panels),
                       all_variables_located=sum(p['all_variables_located'] for p in panels if p['panel']==name),
                       all_exact_basis=sum(p['all_exact_basis'] for p in panels if p['panel']==name))
                       for name in review['candidate_panels']})
    write_csv(out/'formal_c1_gates.csv', gates, list(gates[0]) if gates else ('project_id','gate','status'))
    write_csv(out/'formal_c1_panel_comparison.csv', panels, list(panels[0]) if panels else ('project_id','panel','criteria'))
    (out/'formal_c1_release.json').write_text(canonical(receipt)+'\n', encoding='utf8')
    return dict(formal_C1=bool(receipt['formally_releasable']), formal_c1_projects_checked=receipt['projects_checked'],
                formal_c1_signed_eligible=receipt['projects_with_all_gates'],
                formal_c1_releasable=len(receipt['formally_releasable']))
