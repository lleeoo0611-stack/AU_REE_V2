"""Read-only, source-scoped export of the existing Census to the 52-column contract."""
import csv
import json
import math
import sqlite3
from collections import Counter,defaultdict
from pathlib import Path
from .store import canonical,digest,filehash
from .evidence import load_claims,claim_evidence_ids
from .selection import current_evidence_view,choose
from .pdf_extract import project_registry

STATES={'WA':'西澳大利亞州','SA':'南澳大利亞州','NT':'北領地','VIC':'維多利亞州','NSW':'新南威爾斯州','QLD':'昆士蘭州','TAS':'塔斯馬尼亞州'}
ELEMENTS=('La2O3','CeO2','Pr6O11','Nd2O3','Sm2O3','Eu2O3','Gd2O3','Tb4O7','Dy2O3','Ho2O3','Er2O3','Tm2O3','Yb2O3','Lu2O3','Y2O3')
MAGNET=('Nd2O3','Pr6O11','Tb4O7','Dy2O3')
HEAVY=('Tb4O7','Dy2O3','Ho2O3','Er2O3','Tm2O3','Yb2O3','Lu2O3','Y2O3')


def resource_bundle(observations):
    """Require one source/statement/scope/date. Never add nested resource scopes."""
    grouped=defaultdict(list)
    for o in observations:
        if o['status']=='AUTO_VALIDATED' and o['variable'] in ('ore_mt','grade','contained_treo_kt') and o['basis']=='TREO':
            grouped[(o['source_sha'],o['statement_id'],o['scope'],o['effective_date'])].append(o)
    options=[]
    for key,rows in grouped.items():
        values={};invalid=False
        for variable in ('ore_mt','grade','contained_treo_kt'):
            found=[r for r in rows if r['variable']==variable]
            distinct={(r['value'],r['unit'],r['basis']) for r in found}
            if len(distinct)>1:invalid=True
            if found:values[variable]=found[0]
        if invalid or not {'ore_mt','grade'}<=values.keys():continue
        ore,grade=values['ore_mt'],values['grade']
        if ore['unit']!='Mt' or grade['unit'] not in ('ppm','%'):continue
        if not all(isinstance(r['value'],(int,float)) and math.isfinite(r['value']) for r in values.values()):continue
        pct=grade['value']/10000 if grade['unit']=='ppm' else grade['value']
        if ore['value']<=0 or not 0<pct<=100:continue
        calculated=ore['value']*pct*10
        reported=values.get('contained_treo_kt');rounding={}
        if reported:
            if reported['unit'] not in ('kt','kt TREO') or reported['value']<0:continue
            half_ore=json.loads(ore['raw']).get('rounding_half_width') or 0
            half_grade=json.loads(grade['raw']).get('rounding_half_width') or 0
            factor=.001 if grade['unit']=='ppm' else 10
            lo=(ore['value']-half_ore)*(grade['value']-half_grade)*factor
            hi=(ore['value']+half_ore)*(grade['value']+half_grade)*factor
            rounding=dict(lower_kt=lo,upper_kt=hi)
            if not lo-1e-8<=reported['value']<=hi+1e-8:continue
        value=dict(ore_mt=ore['value'],grade_pct=pct,contained_treo_kt=reported['value'] if reported else calculated)
        options.append(dict(evidence_id=digest(key),source_sha256=key[0],statement_id=key[1],scope=key[2],effective_date=key[3],
            basis='TREO',value=value,observations=rows,contained_method='REPORTED' if reported else 'ORE_MT_X_GRADE_PERCENT_X_10',rounding=rounding))
    selected,reason=choose(options,('scope','basis'))
    return selected,reason


def complete_sum(elements,required):
    return sum(elements[k] for k in required) if all(k in elements and elements[k] is not None for k in required) else None


def export_summary(root,database,run_dir,out,template=None,cutoff='2026-11-05',review_ledger=None,asset_roots=None):
    root=Path(root).resolve();database=Path(database).resolve();run_dir=Path(run_dir).resolve();out=Path(out).resolve()
    if out==root or out==database.parent or root in out.parents and out.relative_to(root).parts[0] in ('data','config','src'):
        raise ValueError('SUMMARY_OUTPUT_MUST_BE_ISOLATED')
    columns=json.loads((Path(__file__).resolve().parents[2]/'config/project_summary_columns.json').read_text('utf8'))
    if template:
        with Path(template).open(encoding='utf-8-sig',newline='') as stream:given=next(csv.reader(stream))
        if given!=columns:raise ValueError('TEMPLATE_COLUMNS_DO_NOT_MATCH_CONTRACT')
    snapshots=json.loads((run_dir/'snapshot_lock.json').read_text('utf8'))
    configuration=json.loads((run_dir/'configuration.json').read_text('utf8'));research=configuration['research']
    claims,claims_sha=load_claims(root,configuration['claims_sha256'])
    if filehash(root/'data/claims.json')!=claims_sha:raise ValueError('REGISTRY_AND_FROZEN_CLAIMS_DIFFER')
    selected={s['sha256']:s for s in snapshots if (s.get('available_date') or '')<=cutoff and (s.get('publication_date') or '')<=cutoff}
    if not selected:raise ValueError('EMPTY_SELECTED_SOURCE_LOCK')
    approved_studies=set()
    if configuration.get('study_cases.json_sha256'):
        study_file=root/'data/study_cases.json'
        if filehash(study_file)!=configuration['study_cases.json_sha256']:raise ValueError('FROZEN_STUDY_CASES_DIFFER')
        approved_studies={digest(c) for c in json.loads(study_file.read_text('utf8'))['cases']}
    before=filehash(database);db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[];trace=[];diagnostics=[];verified=set();inventory=[];supplement=None
    def verify(sha):
        if sha in verified:return
        source=selected[sha]
        if filehash(root/source['path'])!=sha:raise ValueError('SUMMARY_SOURCE_HASH_MISMATCH')
        verified.add(sha)
    def add_trace(pid,column,value,sha,locator,method,scope='',obs_ids=(),review_id=None):
        if sha:verify(sha)
        entry=dict(project_id=pid,column=column,value=value,source_sha256=sha,
            source_url=selected.get(sha,{}).get('url',''),locator=locator,method=method,scope=scope,observation_ids=canonical(list(obs_ids)))
        if review_ledger:
            matches=[r for r in (supplement or {}).get('receipts',[]) if r['project_id']==pid and r['source_sha256']==sha and (not scope or r['scope']==scope) and (not review_id or r['review_id']==review_id)]
            entry.update(effective_date=matches[0]['effective_date'] if matches else '',
                effective_date_role=matches[0]['effective_date_role'] if matches else '',
                date_precision=matches[0]['date_precision'] if matches else '',review_ids=canonical([r['review_id'] for r in matches]),
                acquired_through=selected.get(sha,{}).get('available_date',''),
                review_methods=canonical(sorted({m for receipt in matches for m in receipt.get('review_methods',[])})))
            entry.update(publication_date=selected.get(sha,{}).get('publication_date',''),
                publication_date_role=selected.get(sha,{}).get('publication_date_role',''),document_issue_date=selected.get(sha,{}).get('document_issue_date',''))
            entry.update(publication_date_precision=selected.get(sha,{}).get('publication_date_precision',''),
                publication_date_interval=canonical(selected.get(sha,{}).get('publication_date_interval')),
                source_kind=selected.get(sha,{}).get('source_kind',''),
                effective_date_interval=canonical(matches[0].get('effective_date_interval')) if matches else '')
        # Current-only provenance: a later scoped replacement supersedes this cell.
        trace[:]=[r for r in trace if (r['project_id'],r['column'])!=(pid,column)]
        trace.append(entry)
    try:
        active=claim_evidence_ids(claims)
        current=current_evidence_view(db,list(selected.values()),cutoff,active,
            research.get('evidence_resolution',{}).get('document_pipeline',{}).get('validation_version'),research.get('candidate_version'),claims_data=claims)
        mapping={}
        for r in db.execute("SELECT parent_id,child_id,source_sha FROM relations WHERE relation='DOCUMENT_SUPPORTED_SAME_PROJECT'"):
            if r['source_sha'] in selected:
                if r['child_id'] in mapping and mapping[r['child_id']]!=r['parent_id']:raise ValueError('AMBIGUOUS_PROJECT_MAPPING')
                mapping[r['child_id']]=r['parent_id']
        def canonical_id(pid):
            seen=set()
            while pid in mapping:
                if pid in seen:raise ValueError('CYCLIC_PROJECT_MAPPING')
                seen.add(pid);pid=mapping[pid]
            return pid
        projects=project_registry(root,db,list(selected.values()),mapping={p:canonical_id(p) for p in mapping})
        if review_ledger:
            from .asx_validation import validate_reviews
            supplement=validate_reviews(review_ledger,asset_roots or {},projects,cutoff)
            selected.update(supplement['sources'])
        records=defaultdict(list);observations=defaultdict(list);studies=defaultdict(list)
        for r in db.execute('SELECT r.*,e.kind,e.native_id FROM records r JOIN entities e USING(entity_id)'):
            if (r['entity_id'],r['source_sha']) not in current['record_ids']:continue
            d=dict(r);d.update(current['record_values'].get((r['entity_id'],r['source_sha']),{}));records[canonical_id(r['entity_id'])].append(d)
        for o in db.execute("SELECT * FROM observations WHERE status='AUTO_VALIDATED'"):
            if o['obs_id'] in current['observation_ids']:observations[canonical_id(o['entity_id'])].append(dict(o))
        for s in db.execute('SELECT * FROM study_cases'):
            if s['source_sha'] not in selected or s['effective_date']>cutoff or digest(json.loads(s['raw'])) not in approved_studies:continue
            studies[canonical_id(s['project_id'])].append(dict(s))
        if supplement:
            for pid,extra in supplement['observations'].items():observations[pid].extend(extra)
            for pid,extra in supplement['studies'].items():
                # The ledger explicitly selects a scoped new engineering case;
                # original cases remain in the untouched source SQLite.
                studies[pid]=extra
        for p in projects:
            pid=p['entity_id'];row=dict.fromkeys(columns,'');rs=records[pid];obs=observations[pid]
            def put(column,value,sha='',locator='',method='SOURCE_REPORTED',scope='',obs_ids=(),review_id=None):
                if value is None or value=='':return
                row[column]=value;add_trace(pid,column,value,sha,locator,method,scope,obs_ids,review_id)
            def pick_record(key):
                eligible=[r for r in rs if r.get(key) is not None and r.get(key)!='']
                if not eligible:return None
                eligible.sort(key=lambda r:(selected[r['source_sha']].get('publication_date') or '',r['source_sha']),reverse=True)
                return eligible[0]
            identity=next((s for s in selected.values() if s['key']==p['identity_source']),None)
            put('專案ID',pid,method='EXISTING_CANONICAL_PROJECT_RELATION')
            put('專案名稱',p['name'],identity['sha256'] if identity else '',method='EXISTING_PROJECT_REGISTRY')
            put('國家','澳洲',method='AUSTRALIAN_CENSUS_SCOPE')
            state=pick_record('state')
            if state:
                code=state['state'];sha=state['source_sha'];name=STATES.get(code,code)
                put('州省地區',name,sha,method='SOURCE_STATE_CODE_LABEL');put('所在地_中文','澳洲（'+name+'）',sha,method='SOURCE_STATE_CODE_LABEL')
                put('所在地_英文','Australia ('+code+')',sha,method='SOURCE_STATE_CODE_LABEL')
            # Keep coordinates as a pair from the same record.
            coords=[r for r in rs if r.get('longitude') is not None and r.get('latitude') is not None]
            coords.sort(key=lambda r:(selected[r['source_sha']].get('publication_date') or '',r['source_sha']),reverse=True)
            if coords:
                put('緯度',coords[0]['latitude'],coords[0]['source_sha'],method='REPRESENTATIVE_POINT_NOT_BOUNDARY')
                put('經度',coords[0]['longitude'],coords[0]['source_sha'],method='REPRESENTATIVE_POINT_NOT_BOUNDARY')
            deposit=pick_record('deposit_type')
            if deposit:put('礦床型態',deposit['deposit_type'],deposit['source_sha'])
            owners=[]
            for r in rs:
                raw=json.loads(r['raw'])
                owner=raw.get('owner') or raw.get('developer') or raw.get('company')
                if owner:owners.append((selected[r['source_sha']].get('publication_date') or '',str(owner),r['source_sha']))
            if owners:
                latest=max(o[0] for o in owners);same=[o for o in owners if o[0]==latest]
                if len({o[1] for o in same})==1:put('開發商',same[0][1],same[0][2])
            stages=[o for o in obs if o['variable']=='study_maturity_ord']
            if stages:
                latest=max(o['effective_date'] for o in stages);same=[o for o in stages if o['effective_date']==latest]
                if len({o['value'] for o in same})==1:
                    labels={2:'已揭露完成 Scoping Study',3:'已揭露完成 PFS',4:'已揭露完成 DFS'}
                    o=same[0]
                    if o['value'] in labels:put('開發階段',labels[o['value']]+'（'+latest+'）',o['source_sha'],o['locator'],'DATED_STUDY_DISCLOSURE_NOT_CURRENT_OPERATING_STATUS',o['scope'],[o['obs_id']])
            resource_obs=obs
            if supplement and pid in supplement['resource_preferences']:
                contract=supplement['resource_contracts'][pid]
                resource_obs=[o for o in obs if (o['source_sha'],o['scope'],o['statement_id'],o['effective_date'])==contract]
            bundle,reason=resource_bundle(resource_obs)
            if bundle:
                sha=bundle['source_sha256'];scope=bundle['scope'];ids=[o['obs_id'] for o in bundle['observations']]
                label=(supplement or {}).get('resource_labels',{}).get(pid)
                if label:
                    put('專案名稱',row['專案名稱']+' — '+label['label']+' resource scope',sha,
                        method='EXISTING_PROJECT_WITH_EXPLICIT_RESOURCE_SUBSCOPE_LABEL',scope=scope)
                for variable,column in [('ore_mt','礦石蘊藏量_Mt'),('grade_pct','TREO品位_pct'),('contained_treo_kt','總TREO蘊藏量_kt')]:
                    method=bundle['contained_method'] if variable=='contained_treo_kt' else 'SAME_SOURCE_STATEMENT_SCOPE_DATE'
                    put(column,bundle['value'][variable],sha,'; '.join(sorted({o['locator'] for o in bundle['observations']})),method,scope,ids)
                put('有TREO資源估計','是',sha,method='COMPLETE_SOURCE_BOUND_RESOURCE_PAIR',scope=scope)
                put('資料來源名稱',selected[sha]['key'],sha);put('資料來源URL',selected[sha]['url'],sha)
                same=[o for o in obs if (o['source_sha'],o['statement_id'],o['scope'],o['effective_date'])==
                      (sha,bundle['statement_id'],scope,bundle['effective_date'])]
                shares=[o for o in same if o['variable']=='magnet_reo_share_pct' and o['unit']=='%' and o['basis'] in ('PrNdDyTb_OXIDES_OVER_TREO','PrNdDyTb_REO_DIV_TREO') and 0<=o['value']<=100]
                if shares and len({o['value'] for o in shares})==1:
                    put('磁鐵稀土佔TREO_pct',shares[0]['value'],sha,shares[0]['locator'],scope=scope,obs_ids=[shares[0]['obs_id']])
                    put('磁鐵稀土氧化物蘊藏量_kt',bundle['value']['contained_treo_kt']*shares[0]['value']/100,sha,shares[0]['locator'],'TREO_KT_X_MAGNET_SHARE_PERCENT',scope,ids+[shares[0]['obs_id']])
                elements={}
                for oxide in ELEMENTS:
                    eo=[o for o in same if o['basis']==oxide and o['unit']=='ppm' and json.loads(o['raw']).get('material_basis')=='RESOURCE_ORE_GRADE_OXIDE_PPM']
                    if eo and len({o['value'] for o in eo})==1 and 0<=eo[0]['value']<=1000000:
                        elements[oxide]=bundle['value']['ore_mt']*eo[0]['value']*.001
                        column=next(c for c in columns if c.startswith(oxide+'_'))
                        put(column,elements[oxide],sha,eo[0]['locator'],'ORE_MT_X_OXIDE_PPM_X_0_001',scope,[eo[0]['obs_id']]+ids)
                if elements:
                    put('已公布元素數_共15項',len(elements),sha,scope=scope)
                    put('已公布元素總和_kt',sum(elements.values()),sha,method='SUM_AVAILABLE_MATCHED_OXIDES_NOT_TOTAL_RESOURCE',scope=scope)
                    if bundle['value']['contained_treo_kt']>0:put('元素總和/TREO',sum(elements.values())/bundle['value']['contained_treo_kt'],sha,method='AVAILABLE_OXIDE_SUM_DIVIDED_BY_MATCHED_TREO',scope=scope)
                    put('元素數據一致性檢查','部分元素；未進行完整15項閉合檢查' if len(elements)<15 else
                        '15項氧化物總和與TREO於來源有效位數範圍內一致' if supplement and sha in supplement['sources'] else
                        '15項已齊；須依來源有效位數檢查閉合',sha,scope=scope)
                for required,column in [(('Nd2O3','Pr6O11'),'NdPr蘊藏量_kt_需兩者皆公布'),(HEAVY,'完整重稀土組合蘊藏量_kt_需8元素皆公布'),(MAGNET,'磁性元素重算值_NdPrTbDy_kt')]:
                    value=complete_sum(elements,required)
                    if value is not None:put(column,value,sha,method='SUM_COMPLETE_MATCHED_OXIDE_SET',scope=scope)
                if complete_sum(elements,MAGNET) is not None:put('四項磁性元素皆公布','是',sha,scope=scope)
                # The template's HTML comparison belongs to its original HTML data;
                # no independent HTML comparator exists in this Census export.
            # Forecast products belong to their engineering study scope, not the
            # global resource scope. Bench test endpoints are not plant products.
            models=[s for s in studies[pid] if s['scale'] in ('SCOPING_MODEL','PFS_MODEL','DFS_MODEL','DFS_REFERENCED')]
            for column,parameter in [('預估年產TREO_t_per_year','average_annual_treo_product_t'),
                                     ('預估年產NdPr_t_per_year','average_annual_ndpr_product_t'),
                                     ('預估年產重稀土_t_per_year','average_annual_hreo_product_t')]:
                options=[]
                for s in models:
                    d=json.loads(s['raw']);v=d.get('parameters',{}).get(parameter)
                    if isinstance(v,(int,float)) and math.isfinite(v) and v>=0:
                        options.append(dict(evidence_id=s['case_id'],source_sha256=s['source_sha'],effective_date=s['effective_date'],
                            scope=s['scope'],endpoint=s['endpoint'],element=s['element'],scale=s['scale'],value=v,locator=d['locator'],
                            derivation=d.get('parameter_derivations',{}).get(parameter)))
                forecast,_=choose(options,('scope','endpoint','element','scale'))
                if forecast:
                    put(column,forecast['value'],forecast['source_sha256'],forecast['locator'],'DATED_ENGINEERING_FORECAST_T_PER_YEAR_NOT_OPERATING_OUTPUT',forecast['scope'])
                    if review_ledger:trace[-1]['forecast_derivation']=canonical(forecast.get('derivation'))
            products=[dict(evidence_id=s['case_id'],source_sha256=s['source_sha'],effective_date=s['effective_date'],
                scope=s['scope'],endpoint=s['endpoint'],scale=s['scale'],value=s['endpoint'],locator=json.loads(s['raw'])['locator']) for s in models]
            product,_=choose(products,('scope','endpoint','scale'))
            if product:
                labels={'CALCINED_MIXED_REO':'煅燒混合稀土氧化物','MINERAL_CONCENTRATE':'礦物精礦','MREC':'混合稀土碳酸鹽','REEC':'稀土精礦'}
                put('產品/產出',labels.get(product['value'],product['value'])+'（'+product['scale']+'）',product['source_sha256'],product['locator'],'DATED_ENGINEERING_PRODUCT_ENDPOINT_NOT_OPERATING_OUTPUT',product['scope'])
            docs={r['source_sha'] for r in rs if selected[r['source_sha']]['kind']=='pdf'}|{o['source_sha'] for o in obs if selected[o['source_sha']]['kind']=='pdf'}
            if docs:put('有來源文件','是',sorted(docs)[0],method='VERIFIED_PDF_SOURCE_PRESENT_NOT_COMPLETENESS')
            if not row['資料來源URL'] and identity:
                put('資料來源名稱',identity['key'],identity['sha256']);put('資料來源URL',identity['url'],identity['sha256'])
            for attribute in (supplement or {}).get('attributes',{}).get(pid,[]):
                put(attribute['column'],attribute['value'],attribute['source_sha'],'physical PDF p'+str(attribute['evidence']['page']),
                    'SOURCE_REVIEWED_ATTRIBUTE_NOT_CURRENT_LEGAL_CERTIFICATION',review_id=attribute['review_id'])
            for column in columns:
                if row[column]=='':
                    why=(reason if column in ('礦石蘊藏量_Mt','TREO品位_pct','總TREO蘊藏量_kt') else
                         'NO_SOURCE_BOUND_LISTING_STATUS' if column=='未上市公司' else
                         'NO_APPROVED_TEMPLATE_CLASSIFICATION_CODEBOOK' if column in ('礦床型態代碼','開發階段代碼','開發階段類別') else
                         'NO_INDEPENDENT_HTML_COMPARATOR' if column=='重算磁性元素-HTML磁性稀土_kt' else
                         'NO_COMPLETE_SAME_SCOPE_EIGHT_HEAVY_OXIDE_SET' if column=='完整重稀土組合蘊藏量_kt_需8元素皆公布' else
                         ('NO_COMPATIBLE_SOURCE_REVIEWED_ENGINEERING_FORECAST' if supplement else 'NO_COMPATIBLE_FROZEN_ENGINEERING_FORECAST') if column.startswith('預估年產') else
                         'NO_COMPATIBLE_VERIFIED_FIELD; BLANK_IS_UNKNOWN')
                    d=dict(project_id=pid,column=column,reason=why)
                    deferred=(supplement or {}).get('deferred_fields',{}).get(pid,{}).get(column)
                    if deferred:d.update(reason=deferred['reason'],source_sha256=deferred['source_sha256'],physical_page=deferred['evidence']['page'],review_id=deferred['review_id'])
                    diagnostics.append(d)
            rows.append(row)
        pids={r['專案ID'] for r in rows}
        for eid,rs in sorted(records.items()):
            r=sorted(rs,key=lambda r:r['source_sha'])[0]
            inventory.append(dict(entity_id=eid,kind=r['kind'],name=r['name'],included_in_project_summary=eid in pids,
                source_sha256=r['source_sha'],unit_of_analysis='EXISTING_CENSUS_ENTITY_NOT_AUTOMATIC_PROJECT_ADMISSION'))
    finally:db.close()
    if filehash(database)!=before:raise ValueError('READ_ONLY_DATABASE_CHANGED_DURING_EXPORT')
    out.mkdir(parents=True,exist_ok=True)
    def write(name,data,fields):
        with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fields);w.writeheader();w.writerows(data)
    write('專案總表.csv',rows,columns)
    write('field_provenance.csv',trace,['project_id','column','value','source_sha256','source_url','locator','method','scope','observation_ids']+
        (['effective_date','effective_date_role','date_precision','review_ids','acquired_through','publication_date','publication_date_role','document_issue_date',
          'publication_date_precision','publication_date_interval','source_kind','effective_date_interval','forecast_derivation','review_methods'] if review_ledger else []))
    write('missing_fields.csv',diagnostics,['project_id','column','reason']+(['source_sha256','physical_page','review_id'] if review_ledger else []))
    write('census_inventory.csv',inventory,['entity_id','kind','name','included_in_project_summary','source_sha256','unit_of_analysis'])
    result=dict(version='census-project-summary-v1',cutoff=cutoff,rows=len(rows),columns=len(columns),
        unique_project_ids=len({r['專案ID'] for r in rows}),database_sha256=before,claims_sha256=claims_sha,
        snapshot_lock_sha256=filehash(run_dir/'snapshot_lock.json'),configuration_sha256=filehash(run_dir/'configuration.json'),
        columns_sha256=digest(columns),filled_counts={c:sum(r[c]!='' for r in rows) for c in columns},
        verified_source_hashes=len(verified),database_modified=False,census_by_kind=dict(Counter(r['kind'] for r in inventory)),
        limitations=['SOURCE_SCOPED_MINERAL_RESOURCES_NOT_AUTOMATIC_ORE_RESERVES','REPRESENTATIVE_POINTS_NOT_BOUNDARIES',
        'UNKNOWN_NOT_ZERO_OR_FALSE','DERIVATIONS_DECLARED_IN_FIELD_PROVENANCE','NO_AUTOMATIC_PROMOTION_OF_NEW_ASX_CANDIDATES',
        'HREE8=Tb,Dy,Ho,Er,Tm,Yb,Lu,Y; Gd_EXCLUDED_TO_MATCH_TEMPLATE','NO_HTML_COMPARATOR_IN_CENSUS_EXPORT'],
        output_hashes={p.name:filehash(p) for p in out.glob('*.csv')})
    if supplement:
        result.update(version='census-project-summary-v2-reviewed-asx',review_ledger_sha256=supplement['ledger_sha256'],
            acquired_through=supplement['acquired_through'],validated_reviews=supplement['receipts'],
            projection='READ_ONLY_CANONICAL_CENSUS_PLUS_SOURCE_VALIDATED_OBSERVATIONS_NO_SECOND_RESEARCH_DATABASE')
        result['limitations'].remove('NO_AUTOMATIC_PROMOTION_OF_NEW_ASX_CANDIDATES')
        result['limitations'].append('IMAGE_CELL_TRANSCRIPTIONS_ARE_VISUALLY_REVIEWED_NOT_INDEPENDENT_OCR')
        result['limitations'].append('ONLY_SOURCE_REVIEW_LEDGER_VALUES_PROMOTED;NOT_FORMAL_C1_OR_INDEPENDENT_APPROVAL')
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return result
