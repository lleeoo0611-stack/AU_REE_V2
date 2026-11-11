"""Acceptance for the specific 2026-11-11 approvals, not source authentication.

Read-only: validates the unchanged 53-column core and cell-level authorization.
Complete government snapshot reconstruction and independent final replay hashes
remain mandatory caller checks; this module never treats one candidate as proof
of inventory-wide uniqueness.
"""
import json
import math
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from .coverage_task_audit import read_csv, compare_projections
from .iteration_review import audit_summary
from .stage_rules import proposed_decisions as stage_proposals, decision_records, stage_rule_fills
from .official_location_adapters import proposed_decisions as location_proposals, DATASETS, ROLE, native_state, normalized_name
from .scoped_oxide_exceptions import SPLINTER, CIRCLE, RULES, cerium_factors
from .project_summary import ELEMENTS, MAGNET

NULL_IDS = frozenset(('stage-operating_requires_design_capacity_review-20261111',
    'stage-withdrawal_requires_researcher_review-20261111',
    'official-location-sa_projects_major-20261111', 'official-location-sa_projects_developing-20261111'))
SCOPED_IDS = {SPLINTER[0]: 'task4-splinter-ce2o3-to-ceo2', CIRCLE[0]: 'task4-circle-valley-combined-ndpr'}
CHANGES = {SPLINTER[0]: {'已公布元素數_共15項', '已公布元素總和_kt', '元素數據一致性檢查'},
           CIRCLE[0]: {'元素數據一致性檢查'}}


def require(condition, reason):
    if not condition:
        raise ValueError('APPROVED_COVERAGE_'+reason)


def validate_decisions(decisions):
    expected = stage_proposals()+location_proposals()
    for identity in (SPLINTER, CIRCLE):
        expected.append(dict(decision_id=SCOPED_IDS[identity[0]], rule=RULES[identity[0]],
            project_id=identity[0], scope=dict(statement_id=identity[1], source_sha256=identity[2])))
    records = decision_records(decisions)
    require(all(isinstance(d, dict) for d in records), 'DECISION_RECORD')
    indexed = {d.get('decision_id'): d for d in records}
    require(len(indexed)==len(records)==19 and set(indexed)=={d['decision_id'] for d in expected}, 'DECISION_SET')
    for e in expected:
        d=indexed[e['decision_id']]
        require(all(d.get(k)==e.get(k) for k in ('rule','scope','project_id')), 'DECISION_SCOPE')
        require(d.get('decided_by')==(None if e['decision_id'] in NULL_IDS else 'USER_EXPLICIT_APPROVAL'), 'DECISION_APPROVAL')
        require(d.get('decided_date')=='2026-11-11', 'DECISION_DATE')
        if e['decision_id'] not in NULL_IDS:
            require(isinstance(d.get('approval_evidence'),str) and bool(d['approval_evidence'].strip()), 'DECISION_EVIDENCE')
    return indexed


def _csv_equivalent(value):
    # The in-memory native provenance precedes CSV serialization: None becomes
    # empty, numbers/bools become strings, and optional empty columns are added.
    if isinstance(value, dict):
        return {k:_csv_equivalent(v) for k,v in value.items() if v is not None and v != ''}
    if isinstance(value, list):
        return [_csv_equivalent(v) for v in value]
    return '' if value is None else str(value)


def _number(value, expected):
    try:
        number=float(value)
        return math.isfinite(number) and math.isclose(number,float(expected),rel_tol=1e-12,abs_tol=1e-12)
    except (TypeError, ValueError):
        return False


def _chemistry(old, new, trace, column, traces):
    pid=old['專案ID']; identity=SPLINTER if pid==SPLINTER[0] else CIRCLE
    meta=json.loads(trace['locator'])
    require(meta.get('decision_id')==SCOPED_IDS[pid] and meta.get('statement_id')==identity[1]
            and meta.get('source_sha256')==trace['source_sha256']==identity[2]
            and meta.get('scope')==trace['scope'] and bool(meta.get('effective_date')) and bool(meta.get('ore_cell')), 'CHEMISTRY_SCOPE')
    require(_number(meta.get('ore_mt'), old['礦石蘊藏量_Mt']), 'CHEMISTRY_ORE')
    if pid==SPLINTER[0]:
        complete=json.loads(traces[(pid,'元素數據一致性檢查')]['locator'])
        require(all(k in complete and complete[k]==v for k,v in meta.items()), 'CHEMISTRY_PROOF_CONFLICT')
        meta=complete
    ore=float(old['礦石蘊藏量_Mt'])
    def cell(name):
        c=meta.get(name,{})
        require(c.get('unit')=='ppm' and c.get('page') and c.get('bbox') and c.get('row_bbox')
                and c.get('section_id') and _number(c.get('value'),str(c.get('original_token','')).replace(',','')), 'CHEMISTRY_NATIVE_CELL')
        return float(c['value'])
    if pid==CIRCLE[0]:
        require(trace['method']=='SOURCE_COMBINED_NDPR_OXIDE_PPM_X_ORE_MT' and meta.get('definition')=='NdPr = Nd2O3 + Pr6O11' and meta.get('definition_page')==2, 'NDPR_METHOD')
        expected={'NdPr蘊藏量_kt_需兩者皆公布': ore*cell('native_ndpr')*.001,
            '元素數據一致性檢查':old['元素數據一致性檢查']+'；NdPr為來源公布之合計氧化物品位，依研究者決定填入；Nd、Pr個別值未公布'}
        require(column in expected, 'NDPR_COLUMN')
    else:
        factors=cerium_factors(); ce=cell('native_ce2o3')
        require(meta.get('mode')=='CERIUM_STOICHIOMETRIC_CONVERSION' and meta.get('atomic_weights')=={'Ce':factors['Ce'],'O':factors['O']}
                and _number(meta.get('conversion_factor'),factors['ce2o3_to_ceo2']) and meta.get('basis_proof'), 'CERIUM_FACTOR')
        ce_kt=ore*ce*factors['ce2o3_to_ceo2']*.001
        elements={e:float(next(v for c,v in new.items() if c.startswith(e+'_'))) for e in ELEMENTS if any(c.startswith(e+'_') and v for c,v in new.items())}
        total=(cell('source_treo')-ce+ce*factors['ce2o3_to_ceo2'])*ore*.001
        method='SOURCE_TREO_PLUS_Y_MINUS_CE2O3_PLUS_CEO2'
        require(meta.get('treo_method')==method and meta.get('treo_definition_page')==69, 'CERIUM_TREO_METHOD')
        methods={'CeO2_氧化鈰_kt':'DERIVED_STOICHIOMETRIC_CE2O3_TO_CEO2',
            '已公布元素數_共15項':'COUNT_CANONICAL_INDIVIDUAL_OXIDES', '已公布元素總和_kt':'SUM_AVAILABLE_MATCHED_CANONICAL_OXIDES',
            '元素數據一致性檢查':'RESEARCHER_APPROVED_CANONICAL_OXIDE_CLOSURE',
            '磁鐵稀土氧化物蘊藏量_kt':'SUM_COMPLETE_MATCHED_MAGNET_OXIDES_AFTER_CE_CANONICALIZATION'}
        expected={'CeO2_氧化鈰_kt':ce_kt,'已公布元素數_共15項':len(elements),'已公布元素總和_kt':sum(elements.values()),
            'TREO品位_pct':total/ore/10,'總TREO蘊藏量_kt':total,'有TREO資源估計':'是','元素總和/TREO':sum(elements.values())/total}
        if all(e in elements for e in MAGNET):
            magnetic=sum(elements[e] for e in MAGNET)
            expected.update({'磁鐵稀土氧化物蘊藏量_kt':magnetic,'磁鐵稀土佔TREO_pct':magnetic/total*100})
        if column=='元素數據一致性檢查':
            require(meta.get('closure_shared_ce_conversion_cancels') is True and _number(meta.get('closure_difference_kt'),float(meta['source_sum_minus_treo_ppm'])*ore*.001)
                    and _number(meta.get('closure_rounding_tolerance_kt'),float(meta['closure_rounding_half_width_ppm'])*ore*.001), 'CLOSURE_PROOF')
            delta=meta['closure_difference_kt']; tolerance=meta['closure_rounding_tolerance_kt']
            closure='15項氧化物總和與TREO於來源有效位數範圍內一致' if abs(delta)<=tolerance else '15項閉合差值 '+str(delta)+' kt'
            expected[column]='來源以Ce2O3表示；依研究者決定以化學計量換算為CeO2（係數'+format(factors['ce2o3_to_ceo2'],'.10f')+'）；TREO依'+method+'重算；'+closure
        require(column in expected and trace['method']==methods.get(column,method), 'CERIUM_COLUMN_METHOD')
    value=expected[column]
    require(new[column]==value if isinstance(value,str) else _number(new[column],value), 'CHEMISTRY_VALUE')
    return SCOPED_IDS[pid]


def _location(old, new, traces, decisions):
    require(not old['緯度'] and not old['經度'] and new['緯度'] and new['經度'], 'LOCATION_PAIR')
    pair=[traces[(old['專案ID'],c)] for c in ('緯度','經度')]
    require(pair[0]['scope']==pair[1]['scope'], 'LOCATION_PAIR_SCOPE')
    candidate=json.loads(pair[0]['scope']); dataset=candidate.get('dataset')
    require(dataset in {'WA_MINEDEX','GA_OZMIN','SA_SARIG','QLD_MINOCC','NSW_MINVIEW'}, 'LOCATION_DATASET')
    cfg=DATASETS[dataset]; did='official-location-'+dataset.lower()+'-20261111'
    require(candidate.get('decision_id')==did and did in decisions and candidate.get('layer')==cfg['layer'], 'LOCATION_DECISION')
    require(candidate.get('state')==native_state(old['州省地區']) and (cfg['state'] is None or candidate['state']==cfg['state']), 'LOCATION_STATE')
    require(candidate.get('output_crs')=='EPSG:7844' and candidate.get('original_crs')=='EPSG:'+str(cfg['crs'])
            and candidate.get('position_role')==ROLE and candidate.get('coordinate_source')=='ATTRIBUTES_ONLY', 'LOCATION_CRS_ROLE')
    # Aliased matches require separate source validation; do not trust an arbitrary alias embedded in output.
    require(normalized_name(old['專案名稱']) in {normalized_name(n) for n in candidate.get('names',[])}, 'LOCATION_EXACT_NAME')
    from pyproj import Transformer
    x,y=Transformer.from_crs(cfg['crs'],7844,always_xy=True,allow_ballpark=False).transform(float(candidate['original_longitude']),float(candidate['original_latitude']),errcheck=True)
    require(_number(candidate.get('longitude'),x) and _number(candidate.get('latitude'),y) and 110<=x<=155 and -45<=y<=-9, 'LOCATION_TRANSFORM')
    base=urlsplit(cfg['url']); source=urlsplit(candidate.get('source_url',''))
    require((base.scheme,base.netloc,base.path+('/query' if cfg['kind']=='arcgis' else ''))==(source.scheme,source.netloc,source.path), 'LOCATION_URL')
    for p,field,value in zip(pair,('latitude','longitude'),(y,x)):
        require(p['method']=='AUTO_MATCHED_OFFICIAL_POINT' and p['source_kind']=='GOVERNMENT_SPATIAL_CATALOGUE'
                and p['source_sha256']==candidate.get('source_sha256') and len(p['source_sha256'])==64
                and p['source_url']==candidate['source_url'] and p['acquired_through']==candidate.get('acquired_at')
                and json.loads(p['review_ids'])==[did] and p['value']==format(value,'.10g')
                and p['locator']==cfg['layer']+'; feature '+candidate['feature_id']+'; '+ROLE, 'LOCATION_PROVENANCE')
    return did


def audit_approved_coverage(baseline, after, decisions):
    """Return measured additions/changes after fail-closed approval checks.

    Inputs are 53-column projection directories and decision JSON path/list/dict.
    Raises ValueError on unauthorized cells, metadata, duplicates, or stale audit.
    No publication, network, source writes, or assumptions about addition counts.
    """
    registry=validate_decisions(decisions)
    audits=[]
    for folder in (baseline,after):
        audited=audit_summary(folder)
        require(audited['columns']==53, 'CORE_53_REQUIRED')
        require(json.loads((Path(folder)/'audit.json').read_text('utf8'))==audited, 'STALE_AUDIT')
        audits.append(audited)
    additions,changes=compare_projections(baseline,after,allow_derived=True)
    old={r['專案ID']:r for r in read_csv(Path(baseline)/'專案總表.csv')}
    new={r['專案ID']:r for r in read_csv(Path(after)/'專案總表.csv')}
    prior=read_csv(Path(baseline)/'field_provenance.csv')
    prior_map={(p['project_id'],p['column']):p for p in prior}
    traces={(p['project_id'],p['column']):p for p in read_csv(Path(after)/'field_provenance.csv')}
    stage={pid:{f['column']:f for f in stage_rule_fills(row,prior,{'decisions':list(registry.values())})} for pid,row in old.items()}
    counted=Counter()
    for change in changes:
        require(change['column'] in CHANGES.get(change['project_id'],set()), 'EXISTING_CELL_NOT_AUTHORIZED')
    for item in additions+changes:
        pid,column=item['project_id'],item['column']; p=traces[pid,column]
        if column in ('開發階段代碼','開發階段類別'):
            fill=stage[pid].get(column)
            require(fill is not None and all(p[k]==fill[f] for k,f in [('value','value'),('source_sha256','sha'),('locator','locator'),('method','method')]) and _csv_equivalent(json.loads(p['scope']))==_csv_equivalent(json.loads(fill['scope'])), 'STAGE_REPLAY')
            require(p['source_url']==prior_map[pid,'開發階段']['source_url'], 'STAGE_SOURCE_URL')
            did=json.loads(fill['scope'])['decision_id']
        elif column in ('緯度','經度'):
            did=_location(old[pid],new[pid],traces,registry)
        else:
            require(pid in SCOPED_IDS, 'UNAPPROVED_NEW_COLUMN')
            ore_trace=prior_map[pid,'礦石蘊藏量_Mt']
            require(all(p[k]==ore_trace[k] for k in ('scope','source_sha256','source_url')), 'CHEMISTRY_SELECTED_SOURCE')
            did=_chemistry(old[pid],new[pid],p,column,traces)
        counted[did]+=1
    return dict(passed=True,approved_decisions=15,null_decisions=4,new_cells=len(additions),changed_cells=len(changes),
        additions=additions,changes=changes,cells_by_decision=dict(counted),before=audits[0],after=audits[1],
        government_complete_snapshot_replay_required=True)
