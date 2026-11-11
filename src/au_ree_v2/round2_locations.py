"""Round two offline-only, approval-gated official representative points."""
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from pyproj import Transformer, network

# Offline replay must never download optional PROJ transformation grids.
network.set_network_enabled(False)
from . import official_location_adapters as base

NAME_RULE = 'NORMALIZED_NAME_MATCH'
NT_RULE = 'NT_STRIKE_MGA_TO_GEOGRAPHIC'
APPROVAL_EVIDENCE = '1：G1 選 B、潛力案給、G4 照建議；2：(a) 算完成、(b) 給 B1、(c) 新增 D、(d) 標成X'
SCOPES = {NAME_RULE:'OFFLINE_ARCHIVED_SAME_STATE_UNIQUE_OPERATOR_MATCH', NT_RULE:'ARCHIVED_NT_CSV_VERIFIED_DATUM_ONLY'}
NT_MEMBER_SHA = '8cedb8e7072c9528f4562ab9643f0ec2e211e9a86ad2550338cd1f5b530194b7'
FIELDS = {'WA_MINEDEX':['site_title','short_name','proj_title'], 'GA_OZMIN':['OCCURRENCE_NAME','PROJECT'], 'NSW_MINVIEW':['deposit_name','all_names'], 'QLD_MINOCC':['occur_name'], 'NT_STRIKE':['NAME']}

def normalized_name(value):
    value = str(value or '').split('—',1)[0].casefold()
    value = re.sub(r'[^\w\s]',' ',value)
    value = re.sub(r'\brare\s+earths?\b|\bresource\s+scope\b|\b(?:ree|project|deposit|prospect|exploration|historical)\b',' ',value)
    return ' '.join(value.split())

def operator_name(value):
    return ' '.join(re.sub(r'\b(?:limited|ltd|nl|pty|corporation|corp)\b',' ',re.sub(r'[^\w\s]',' ',str(value or '').casefold())).split())

def decision_for(rule, decisions):
    records = decisions.get('decisions',[]) if isinstance(decisions,dict) else decisions
    hits = [d for d in records if d.get('rule') == rule and d.get('decided_by') == 'USER_EXPLICIT_APPROVAL' and not d.get('superseded_by')]
    if len(hits)>1: raise ValueError('ROUND2_LOCATION_DUPLICATE_DECISION')
    return hits[0] if hits and hits[0].get('decision_id') and hits[0].get('approval_evidence')==APPROVAL_EVIDENCE and hits[0].get('scope')==SCOPES.get(rule) and hits[0].get('decided_date')=='2026-11-11' else None

def transform_nt(easting,northing,zone,datum):
    """Datum must be established from archived dataset metadata by caller."""
    if datum not in ('GDA94','GDA2020'): raise ValueError('NT_DATUM_METADATA_REQUIRED')
    zone=int(zone)
    if zone not in (52,53,54): raise ValueError('NT_MGA_ZONE_INVALID')
    transformer=Transformer.from_crs((28300 if datum=='GDA94' else 7800)+zone,7844,always_xy=True,allow_ballpark=False)
    lon,lat=transformer.transform(float(easting),float(northing),errcheck=True)
    if not 128<=lon<=139 or not -27<=lat<=-10: raise ValueError('NT_COORDINATE_RANGE')
    return lon,lat

def load_candidates(acquisitions, decisions):
    candidates=[]; queue=[]
    for result in acquisitions:
        dataset=result['dataset']
        if dataset=='NT_STRIKE':
            for receipt in result.get('receipts',[]):
                raw=Path(receipt['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=receipt['sha256']: raise ValueError('NT_ARCHIVE_HASH')
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    raw_csv=z.read('MINERALOCCURRENCES.csv')
                if hashlib.sha256(raw_csv).hexdigest()!=NT_MEMBER_SHA: raise ValueError('NT_MEMBER_HASH')
                for a in csv.DictReader(io.StringIO(raw_csv.decode('utf-8-sig'))):
                    if base.REE.search(a['COM_MAJOR']+' '+a['COM_MINOR']):
                        queue.append(dict(dataset=dataset,reason='NT_DATUM_METADATA_REQUIRED',feature_id=a['MODAT_ID'],names=[a['NAME']],state='NT',latitude='',longitude='',operator='',normalized_names=[normalized_name(a['NAME'])],easting=a['EASTING'],northing=a['NORTHING'],zone=a['ZONE_MGA'],source_sha256=receipt['sha256'],member_sha256=NT_MEMBER_SHA))
            continue
        if dataset not in FIELDS or result.get('status')!='COMPLETE' or not base.decision_for(dataset,decisions): continue
        verified=base.verify_acquisition_snapshots(result,decisions)
        for item in verified['features']:
            a=base._attributes(item['feature'])
            try: c=base.normalize_feature(dataset,item['feature'],item['receipt'])
            except (ValueError,TypeError,KeyError) as exc:
                queue.append(dict(dataset=dataset,reason=str(exc),native_attributes=a));continue
            names=[]
            for f in FIELDS[dataset]:
                names.extend(n.strip() for n in re.split('[;|]',str(a.get(f) or '')) if n.strip())
            # Only proj_title is documented as carrying a slash-delimited operator.
            title=str(a.get('proj_title') or '')
            title_name,sep,operator=title.partition(' / ')
            if sep: names=[title_name if n==title else n for n in names]
            c.update(names=names,normalized_names=sorted({normalized_name(n) for n in names}),operator=operator if sep else '',operator_field='proj_title' if dataset=='WA_MINEDEX' else '',project_group=str(a.get('proj_code') or title),project_title=title,decision_id=base.decision_for(dataset,decisions)['decision_id'])
            candidates.append(c)
    return candidates,queue

def match_project(row,candidates,all_rows=()):
    if row.get('緯度') or row.get('經度'): return dict(status='EXISTING_PAIR_UNCHANGED',candidates=[])
    name=normalized_name(row['專案名稱']);state=base.native_state(row.get('州省地區'))
    if state in ('VIC','TAS'):return dict(status='NO_APPROVED_NEW_DATASET_VIC_TAS',candidates=[])
    matches=[c for c in candidates if c['state']==state and name in c['normalized_names']]
    if 'uro' in operator_name(row.get('開發商')) and 'charley creek' in name:
        return dict(status='TENEMENT_SCOPE_REQUIRES_RESEARCHER_DECISION',candidates=[c for c in candidates if c['state']==state and any('charley creek' in n for n in c['normalized_names'])])
    if not matches:
        # Suggestions are review-only; token containment never authorizes a fill.
        suggested=[c for c in candidates if c['state']==state and any(len(n.split())>=2 and (name.startswith(n+' ') or n.startswith(name)) for n in c['normalized_names'] if n)]
        return dict(status='NO_NORMALIZED_NAME_MATCH',candidates=suggested)
    # Expand every matched project group; site-name coincidence cannot pick one site.
    groups={(c['dataset'],c.get('project_group')) for c in matches if c.get('project_group')}
    expanded=[c for c in candidates if c in matches or (c['dataset'],c.get('project_group')) in groups]
    if len(expanded)>1: return dict(status='MULTIPLE_CANDIDATES',candidates=expanded)
    c=matches[0]
    if (c.get('operator_field') or c['dataset']=='WA_MINEDEX') and not operator_name(c['operator']):
        return dict(status='OPERATOR_FIELD_VALUE_MISSING',candidates=matches)
    if c['operator'] and operator_name(c['operator'])!=operator_name(row.get('開發商')):
        return dict(status='OPERATOR_MISMATCH',candidates=matches)
    competing=[r for r in all_rows if r.get('專案ID')!=row.get('專案ID') and base.native_state(r.get('州省地區'))==state and normalized_name(r['專案名稱']) in c['normalized_names'] and (not c['operator'] or operator_name(c['operator'])==operator_name(r.get('開發商')))]
    if competing:return dict(status='POINT_MATCHES_MULTIPLE_RESEARCH_ROWS',candidates=matches)
    return dict(status='AUTO_MATCHED_NORMALIZED_NAME',candidates=matches)

def build_round2_locations(rows, acquisitions, decisions):
    """Returns (fills_by_project, review_rows); never writes or contacts a server."""
    candidates,source_queue=load_candidates(acquisitions,decisions)
    decision=decision_for(NAME_RULE,decisions); fills={};queue=[]
    for row in rows:
        result=match_project(row,candidates,rows)
        if result['status']=='EXISTING_PAIR_UNCHANGED':continue
        if not decision:result['status']='NORMALIZED_NAME_DECISION_REQUIRED'
        if result['status']!='AUTO_MATCHED_NORMALIZED_NAME':
            possible=result['candidates']
            if base.native_state(row.get('州省地區'))=='NT':
                nt=[c for c in source_queue if c.get('dataset')=='NT_STRIKE' and (normalized_name(row['專案名稱']) in c.get('normalized_names',[]) or ('charley creek' in normalized_name(row['專案名稱']) and any('charley creek' in n for n in c.get('normalized_names',[]))))]
                possible=possible+nt
                if nt and result['status']=='NO_NORMALIZED_NAME_MATCH':result['status']='NT_DATUM_METADATA_REQUIRED'
            queue.append(dict(project_id=row['專案ID'],project_name=row['專案名稱'],reason=result['status'],normalized_project_name=normalized_name(row['專案名稱']),candidates=json.dumps(possible,ensure_ascii=False,sort_keys=True)))
            continue
        c=dict(result['candidates'][0]);c.update(distance_check='NO_VERIFIED_DISTANCE_COMPARATOR',match_decision_id=decision['decision_id'],normalized_project_name=normalized_name(row['專案名稱']),scope_note='官方代表點，不是資源範圍或礦權邊界')
        if not c.get('operator_field'):c['qualifier']='NO_OPERATOR_FIELD'
        fills[row['專案ID']]=[dict(column=col,value=c[key],method=NAME_RULE,source_sha=c['source_sha256'],sha=c['source_sha256'],source_url=c['source_url'],scope=json.dumps(c,ensure_ascii=False,sort_keys=True),locator=c['layer']+'; feature '+c['feature_id']+'; '+base.ROLE,decision_id=decision['decision_id'],acquired_at=c['acquired_at']) for col,key in [('緯度','latitude'),('經度','longitude')]]
    return fills,queue
