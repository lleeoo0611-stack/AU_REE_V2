"""Scoped fourth-round merge and blank semantics with reconstructable baseline."""
import copy,json,shutil,subprocess,base64,gzip,hashlib,csv,io
from pathlib import Path
from collections import Counter
from .round2_pipeline import read_csv,write_csv,write_json,FILES
from . import round3_schema as old
from .store import filehash,digest
from .stage_rules import selected_mre
KEEP='AU-d0ce731e1d8198ffaf58'
DROP='AU-ee5ca893d12883df35f1'
ARCHIVE='round4_baseline_archive.json'
VERSION='round4-core-v1'
PRODUCT='產品/產出'
DECIMAL_PROJECT='AU-ff758cad5beb276d327d'
DECIMAL_ALLOWLIST={
 'NdPr蘊藏量_kt_需兩者皆公布':('89.75000000000001','89.75'),
 '完整重稀土組合蘊藏量_kt_需8元素皆公布':('112.49999999999999','112.5'),
 '磁性元素重算值_NdPrTbDy_kt':('104.50000000000001','104.5'),
 'Nd2O3_氧化釹_kt':('70.00000000000001','70'),
 'Sm2O3_氧化釤_kt':('13.750000000000002','13.75'),
 'Tb4O7_氧化鋱_kt':('2.0000000000000004','2'),
 'Er2O3_氧化鉺_kt':('8.999999999999998','9'),
 'Yb2O3_氧化鐿_kt':('10.250000000000002','10.25'),
 'Y2O3_氧化釔_kt':('72.49999999999999','72.5')}


def _json(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)
def _load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def _fields(records,base=()):return list(dict.fromkeys([*base,*[k for r in records for k in r]]))
def _trace(p):return {(r['project_id'],r['column']):r for r in p}
def coverage(rows,trace,repo,missing=()):
    result=old.coverage(rows,trace,old.config(repo))
    ids={r['專案ID']:r for r in rows};excluded=[m for m in missing if m.get('blank_class')=='NOT_APPLICABLE_STAGE' and m['column']==PRODUCT]
    n=len(excluded);x=result['all_retained_columns'];x.update(old.metric(x['filled'],x['denominator']-n))
    for name,tier in [('tier1',True),('tier2',False)]:
        count=sum((not(selected_mre(ids[m['project_id']],trace)[0] is False and not ids[m['project_id']]['總TREO蘊藏量_kt']))==tier for m in excluded)
        x=result['tiered_coverage'][name];x.update(old.metric(x['filled'],x['denominator']-count));x['not_applicable_stage_excluded']=count
    a=result['tiered_coverage']['tier1'];b=result['tiered_coverage']['tier2'];result['tiered_coverage']['combined']=old.metric(a['filled']+b['filled'],a['denominator']+b['denominator'])
    result['not_applicable_stage_excluded']=n
    return result

def classify_gaps(rows,missing,repo):
    """Re-evaluate product eligibility on every stage; never write a product value."""
    ids={r['專案ID']:r for r in rows}
    manifests=_load(Path(repo)/'results/round3-2-2026-11-11/stage_search_manifests.json')
    manifests={m['project_id']:m for m in manifests}
    _,reviews=read_csv(Path(repo)/'results/round2-A-2026-11-11/review_queue.csv')
    byid={r['project_id']:r for r in reviews}
    for m in missing:
        row=ids[m['project_id']]
        if m['column']==PRODUCT:
            if row['開發階段代碼'] in ('A1','A2'):
                m.update(blank_class='NOT_APPLICABLE_STAGE',reason='NO_PRODUCT_BEFORE_STUDY_STAGE',blank_rule_id='round4-product-before-study-v1')
            elif m.get('blank_rule_id')=='round4-product-before-study-v1':
                m.update(blank_class='UNKNOWN',reason='NO_PRODUCT_DISCLOSED',blank_rule_id='default-unknown')
        if m.get('reason')=='NO_APPROVED_TEMPLATE_CLASSIFICATION_CODEBOOK':
            m.update(blank_class='UNKNOWN',blank_rule_id='round4-approved-codebook-v1')
            if m['column'] in ('開發階段代碼','開發階段類別'):
                evidence=manifests.get(m['project_id'],{})
                reasons=sorted({x['reason'] for x in evidence.get('blockers',[])})
                if evidence.get('hits'):reasons.append('KEYWORD_HIT')
                m.update(reason='STAGE_INFERENCE_BLOCKED',blocked_by=_json(reasons or ['NO_ACCEPTED_STAGE_EVIDENCE']),evidence_ref='results/round3-2-2026-11-11/stage_search_manifests.json#'+m['project_id'])
            else:
                e=byid.get(m['project_id'])
                m.update(reason='DEPOSIT_RULE_LEFT_BLANK' if e else 'NO_DEPOSIT_DESCRIPTION_IN_ARCHIVED_SOURCES',blocked_by=e['reason'] if e else 'NO_ACCEPTED_PROJECT_SPECIFIC_DEPOSIT_DESCRIPTION',evidence_ref='results/round2-A-2026-11-11/review_queue.csv#'+m['project_id'])
    return missing

def _write(before,out,rows,trace,missing,repo,archive=None,classification=False):
    before,out,repo=map(Path,(before,out,repo))
    if out.exists():raise ValueError('ROUND4_FRESH_OUTPUT_REQUIRED')
    out.mkdir(parents=True)
    if classification:classify_gaps(rows,missing,repo)
    pf,_=read_csv(before/'field_provenance.csv');mf,_=read_csv(before/'missing_fields.csv')
    for n,fields,data in [('專案總表.csv',list(rows[0]),rows),('field_provenance.csv',_fields(trace,pf),trace),('missing_fields.csv',_fields(missing,mf),missing)]:write_csv(out/n,fields,data)
    shutil.copyfile(before/'census_inventory.csv',out/'census_inventory.csv')
    if archive is not None:write_json(out/ARCHIVE,archive)
    else:shutil.copyfile(before/ARCHIVE,out/ARCHIVE)
    # Retained source archive is still byte-for-byte the third-round archive.
    shutil.copyfile(before/old.ARCHIVE,out/old.ARCHIVE)
    summary=_load(before/'summary.json')
    summary.update(version=VERSION,projects=len(rows),columns=len(rows[0]),columns_sha256=digest(list(rows[0])),classification_enabled=classification,filled_counts={c:sum(bool(r[c]) for r in rows) for c in rows[0]},blank_coverage=dict(blank_class_counts=dict(sorted(Counter(m.get('blank_class','UNKNOWN') for m in missing).items()))),existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED',**coverage(rows,trace,repo,missing))
    summary['output_hashes']={n:filehash(out/n) for n in (*FILES[:4],ARCHIVE,old.ARCHIVE)}
    write_json(out/'summary.json',summary);write_json(out/'audit.json',audit(out,repo))

def merge(before,out,repo):
    before,repo=Path(before),Path(repo)
    cols,rows=read_csv(before/'專案總表.csv');_,trace=read_csv(before/'field_provenance.csv');_,missing=read_csv(before/'missing_fields.csv')
    index={r['專案ID']:r for r in rows};p=_trace(trace)
    if len(rows)!=93 or KEEP not in index or DROP not in index or index[KEEP]['ASX代碼']!='GA8':raise ValueError('ROUND4_MERGE_SCOPE')
    alias=_load(repo/'config/issuer_aliases.json')['aliases'][0]
    decisions=_load(repo/'config/researcher_rule_decisions.json')['decisions']
    if not any(d['decision_id']==alias['decision_id'] and d.get('decided_by')=='USER_EXPLICIT_APPROVAL' for d in decisions):raise ValueError('ROUND4_MERGE_NOT_APPROVED')
    if alias['keep_project_id']!=KEEP or alias['drop_project_id']!=DROP or alias['current_asx']!='GA8' or alias['current_name']!='GoldArc Resources Limited':raise ValueError('ROUND4_ALIAS_SCOPE')
    evidence=alias['evidence']
    roots=_load(repo/'config/asx_local_asset_roots.json')['roots']
    asset_repo=Path(__file__).resolve().parents[2]
    candidates=[(asset_repo / root / 'data/snapshots' / (evidence['sha256']+'.pdf')).resolve() for root in roots.values()]
    originals=[p for p in candidates if p.is_file()]
    if not originals or not any(filehash(p)==evidence['sha256'] for p in originals):raise ValueError('ROUND4_ISSUER_SOURCE_SHA')
    texts={e['physical_page']:e['text'] for e in evidence['evidence']}
    if not all(t in texts.get(13,'') for t in ('Asra Minerals Limited','GoldArc Resources Limited','17 September 2025')) or '30 March 2026' not in texts.get(34,''):raise ValueError('ROUND4_ISSUER_UNPROVEN')
    a,b=index[KEEP],index[DROP];before_row=copy.deepcopy(a);original_developer_trace=copy.deepcopy(p[(KEEP,'開發商')]);changes=[];conflicts=[]
    presentation_files=_load(repo/'config/round4_baseline_presentation.json')['files']
    presrows=old.archive_csv(presentation_files,'專案總表.csv');prestrace=old.archive_csv(presentation_files,'field_provenance.csv')
    archived=dict(project_id=DROP,row=copy.deepcopy(b),provenance=[x for x in trace if x['project_id']==DROP],presentation_row=next(r for r in presrows if r['專案ID']==DROP),presentation_provenance=[r for r in prestrace if r['project_id']==DROP])
    for c in cols:
        av,bv=a[c],b[c]
        if av and bv and av!=bv:conflicts.append(dict(project_id=KEEP,merged_project_id=DROP,column=c,kept_value=av,other_value=bv,kept_provenance=p.get((KEEP,c)),other_provenance=p.get((DROP,c))))
        if not av and bv:
            a[c]=bv;q=copy.deepcopy(p[(DROP,c)]);q.update(project_id=KEEP,merged_from=DROP);trace.append(q);p[(KEEP,c)]=q
        elif av and bv and av==bv:
            p[(KEEP,c)]['merge_supporting_provenance']=_json([copy.deepcopy(p[(DROP,c)])])
        if a[c]:p[(KEEP,c)]['merged_from']=KEEP if av else DROP
    a['開發商']='GoldArc Resources Limited'
    issuer_source=_load(repo/'config/asx_project_identity_reviews.json')['sources']['mt_stirling_goldarc_annual2025']
    if issuer_source['sha256']!=evidence['sha256']:raise ValueError('ROUND4_ISSUER_METADATA_SHA')
    issuer_trace=p[(KEEP,'開發商')]
    issuer_trace.clear()
    issuer_trace.update(project_id=KEEP,column='開發商',value=a['開發商'],former_issuer_name='Asra Minerals Limited',source_sha256=issuer_source['sha256'],source_url=issuer_source['url'],locator='physical PDF pp1,13,34',method='SAME_ISSUER_RENAME_RESEARCHER_APPROVED',scope='ISSUER_RENAME_ONLY_NOT_RESOURCE_EFFECTIVE_DATE',document_issue_date='2026-03-30',publication_date='2026-03-30',publication_date_role='ANNUAL_REPORT_PUBLICATION',publication_date_precision='day',publication_date_interval='null',effective_date='',effective_date_role='',effective_date_interval='',date_precision='',merged_from=KEEP,supporting_provenance=_json([original_developer_trace]),review_ids=_json([alias['decision_id']]))
    for c,v in [('緯度','-28.637343'),('經度','121.077616')]:
        if a[c]!=v:raise ValueError('ROUND4_MINEDEX_POINT_MISMATCH')
        p[(KEEP,c)]['qualifier']='SHARED_DEPOSIT_POINT_RESEARCHER_APPROVED'
    for c in cols:
        if before_row[c]!=a[c] or (KEEP,c) in p:changes.append(dict(project_id=KEEP,column=c,old_value=before_row[c],new_value=a[c],reason='SAME_ISSUER_RENAME_RESEARCHER_APPROVED_VALUE_OR_PROVENANCE'))
        if b[c]:changes.append(dict(project_id=DROP,column=c,old_value=b[c],new_value='',reason='ROW_ARCHIVED_NOT_DELETED'))
    rows=[r for r in rows if r['專案ID']!=DROP];trace=[r for r in trace if r['project_id']!=DROP];missing=[m for m in missing if m['project_id']!=DROP and not index[m['project_id']][m['column']]]
    archive=dict(version='round4-baseline-archive-v1',files=old.pack(before,FILES),presentation_files=presentation_files,merge=dict(keeper=KEEP,dropped=DROP,issuer_evidence=evidence,merged_rows=[archived],merge_conflicts=conflicts,expected_keeper=a,expected_keeper_provenance=[r for r in trace if r['project_id']==KEEP]))
    _write(before,out,rows,trace,missing,repo,archive=archive)
    return [],changes,[],dict(merged_rows=[archived],merge_conflicts=conflicts,merge_coverage_before=old.coverage(old.archive_csv(archive['files'],'專案總表.csv'),old.archive_csv(archive['files'],'field_provenance.csv'),old.config(repo)),merge_coverage_after=coverage(rows,trace,repo,missing))

def classify(before,out,repo):
    _,rows=read_csv(Path(before)/'專案總表.csv');_,trace=read_csv(Path(before)/'field_provenance.csv');_,missing=read_csv(Path(before)/'missing_fields.csv');previous=copy.deepcopy(missing)
    _write(before,out,rows,trace,missing,repo,classification=True)
    _,after=read_csv(Path(out)/'missing_fields.csv');changed=[]
    for a,b in zip(previous,after):
        if any(a.get(k,'')!=b.get(k,'') for k in set(a)|set(b)):changed.append(dict(project_id=a['project_id'],column=a['column'],old_value=_json(a),new_value=_json(b),reason=b['reason']))
    return [],changed,[],{}

def fill(before,out,fills,decisions,repo):
    _,rows=read_csv(Path(before)/'專案總表.csv');_,trace=read_csv(Path(before)/'field_provenance.csv');_,missing=read_csv(Path(before)/'missing_fields.csv');index={r['專案ID']:r for r in rows};known=set(_trace(trace));approved={d['decision_id'] for d in decisions['decisions'] if d.get('decided_by')=='USER_EXPLICIT_APPROVAL'};new=[]
    for f in fills:
        k=f['project_id'],f['column']
        if k[0] not in index or k[1] not in index[k[0]] or index[k[0]][k[1]] or k in known or f['decision_id'] not in approved or str(f['value'])=='':raise ValueError('ROUND4_FILL_NOT_APPROVED_BLANK')
        p=dict(f.get('provenance',{}));p.update(project_id=k[0],column=k[1],value=str(f['value']))
        if not all(p.get(s) for s in ('source_sha256','locator','method')):raise ValueError('ROUND4_FILL_TRACE_REQUIRED')
        p={k:_json(v) if isinstance(v,(list,dict)) else v for k,v in p.items()};index[k[0]][k[1]]=p['value'];trace.append(p);known.add(k);new.append(dict(project_id=k[0],column=k[1],new_value=p['value']))
    _write(before,out,rows,trace,[m for m in missing if not index[m['project_id']][m['column']]],repo,classification=True)
    return new,[]

def audit(folder,repo=None):
    folder=Path(folder);repo=Path(repo) if repo else Path(__file__).resolve().parents[2];s=_load(folder/'summary.json')
    cols,rows=read_csv(folder/'專案總表.csv');_,trace=read_csv(folder/'field_provenance.csv');_,gaps=read_csv(folder/'missing_fields.csv');p=_trace(trace);ids={r['專案ID']:r for r in rows}
    if s['version']=='round4-presentation-v1':return audit_presentation(folder,repo)
    if s['version']!=VERSION:raise ValueError('ROUND4_VERSION')
    if len(ids)!=92 or len(rows)!=92 or DROP in ids or KEEP not in ids or len(cols)!=51:raise ValueError('ROUND4_COHORT')
    values={(r['專案ID'],c):v for r in rows for c,v in r.items() if v}
    if len(p)!=len(trace) or set(p)!=set(values) or any(p[k]['value']!=v for k,v in values.items()):raise ValueError('ROUND4_TRACE_MISMATCH')
    if len(gaps)!=len({(g['project_id'],g['column']) for g in gaps}) or {(g['project_id'],g['column']) for g in gaps}!={(r['專案ID'],c) for r in rows for c,v in r.items() if not v}:raise ValueError('ROUND4_GAPS')
    for n,sha in s['output_hashes'].items():
        if filehash(folder/n)!=sha:raise ValueError('ROUND4_OUTPUT_SHA')
    ar=_load(folder/ARCHIVE)
    for records in (ar['files'],ar['presentation_files']):
        for rec in records.values():old.unpack(rec)
    original=old.archive_csv(ar['files'],'專案總表.csv');origp=old.archive_csv(ar['files'],'field_provenance.csv')
    if ar['merge']['merged_rows'][0]['row']!=next(r for r in original if r['專案ID']==DROP):raise ValueError('ROUND4_MERGE_ARCHIVE')
    for r in original:
        if r['專案ID'] in (KEEP,DROP):continue
        if any(v and ids[r['專案ID']][c]!=v for c,v in r.items()):raise ValueError('ROUND4_EXISTING_VALUE_CHANGED')
    for q in origp:
        if q['project_id'] in (KEEP,DROP):continue
        if any(p[(q['project_id'],q['column'])].get(k,'')!=v for k,v in q.items()):raise ValueError('ROUND4_EXISTING_TRACE_CHANGED')
    for c,v in ar['merge']['expected_keeper'].items():
        if v and ids[KEEP][c]!=v:raise ValueError('ROUND4_KEEPER_VALUE_CHANGED')
    for q in ar['merge']['expected_keeper_provenance']:
        if any(p[(KEEP,q['column'])].get(k,'')!=v for k,v in q.items()):raise ValueError('ROUND4_KEEPER_TRACE_CHANGED')
    if filehash(folder/'census_inventory.csv')!=ar['files']['census_inventory.csv']['sha256']:raise ValueError('ROUND4_INVENTORY_CHANGED')
    if s.get('classification_enabled'):
        check=copy.deepcopy(gaps);classify_gaps(rows,check,repo)
        if check!=gaps:raise ValueError('ROUND4_BLANK_CLASSIFICATION')
    if any(s.get(k)!=v for k,v in coverage(rows,trace,repo,gaps).items()):raise ValueError('ROUND4_COVERAGE')
    return dict(version='round4-audit-v1',projects=len(rows),columns=len(cols),filled_cells=len(values),remaining_blank_cells=len(gaps),provenance_complete=True,missing_diagnostics_complete=True,output_hashes=s['output_hashes'],baseline_reconstructable=True,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED')

def presentation_records(rows,trace,missing,archive):
    oldrows={r['專案ID']:r for r in old.archive_csv(archive['presentation_files'],'專案總表.csv')};oldtrace=_trace(old.archive_csv(archive['presentation_files'],'field_provenance.csv'))
    baseline={r['專案ID']:r for r in old.archive_csv(archive['files'],'專案總表.csv')}
    actual_differences={}
    for pid,base in baseline.items():
        for column,value in base.items():
            if column=='元素數據一致性檢查':continue
            shown=oldrows[pid][column]
            if shown!=value:actual_differences[(pid,column)]=(value,shown)
    allowed={(DECIMAL_PROJECT,c):v for c,v in DECIMAL_ALLOWLIST.items()}
    if actual_differences!=allowed:raise ValueError('ROUND4_UNAPPROVED_PRESENTATION_BASELINE_DIFFERENCE')
    rows=copy.deepcopy(rows);trace=copy.deepcopy(trace);missing=copy.deepcopy(missing);p=_trace(trace)
    trace=[q for q in trace if q['column']!='元素數據一致性檢查'];missing=[m for m in missing if m['column']!='元素數據一致性檢查']
    result=[]
    for r in rows:
        pid=r['專案ID'];row={('總說明' if c=='元素數據一致性檢查' else c):(oldrows[pid]['總說明'] if c=='元素數據一致性檢查' else v) for c,v in r.items()}
        if row['總說明']:trace.append(copy.deepcopy(oldtrace[(pid,'總說明')]))
        else:missing.append(dict(project_id=pid,column='總說明',reason='NO_APPLICABLE_NOTE',blank_class='UNKNOWN',blank_rule_id='default-unknown'))
        # Keep only the previously accepted decimal display corrections, not arbitrary differences.
        for c,v in row.items():
            if c=='總說明' or c not in baseline[pid]:continue
            if oldrows[pid][c]!=baseline[pid][c] and r[c]==baseline[pid][c]:
                if pid==KEEP:continue
                row[c]=oldrows[pid][c];q=p[(pid,c)];q.clear();q.update(copy.deepcopy(oldtrace[(pid,c)]))
        result.append(row)
    return result,trace,missing

def present(source,out,repo):
    source,out,repo=map(Path,(source,out,repo));audit(source,repo)
    _,rows=read_csv(source/'專案總表.csv');pf,trace=read_csv(source/'field_provenance.csv');mf,missing=read_csv(source/'missing_fields.csv');archive=_load(source/ARCHIVE)
    rows,trace,missing=presentation_records(rows,trace,missing,archive)
    if out.exists():raise ValueError('ROUND4_FRESH_PRESENTATION_REQUIRED')
    out.mkdir(parents=True)
    for n,fields,data in [('專案總表.csv',list(rows[0]),rows),('field_provenance.csv',_fields(trace,pf),trace),('missing_fields.csv',_fields(missing,mf),missing)]:write_csv(out/n,fields,data)
    for n in ('census_inventory.csv',ARCHIVE,old.ARCHIVE):shutil.copyfile(source/n,out/n)
    write_json(out/'round4_presentation_core.json',dict(files=old.pack(source,FILES)))
    summary=_load(source/'summary.json');summary.update(version='round4-presentation-v1',columns_sha256=digest(list(rows[0])),filled_counts={c:sum(bool(r[c]) for r in rows) for c in rows[0]},presentation_note_policy='PRESERVE_KEEPER_NOTE_AND_EXISTING_DECIMAL_DISPLAY')
    summary['output_hashes']={n:filehash(out/n) for n in (*FILES[:4],ARCHIVE,old.ARCHIVE,'round4_presentation_core.json')}
    write_json(out/'summary.json',summary);write_json(out/'audit.json',audit_presentation(out,repo))

def audit_presentation(folder,repo):
    folder=Path(folder);s=_load(folder/'summary.json');ar=_load(folder/ARCHIVE);core=_load(folder/'round4_presentation_core.json')['files']
    for r in core.values():old.unpack(r)
    expected=presentation_records(old.archive_csv(core,'專案總表.csv'),old.archive_csv(core,'field_provenance.csv'),old.archive_csv(core,'missing_fields.csv'),ar)
    for name,wanted in zip(('專案總表.csv','field_provenance.csv','missing_fields.csv'),expected):
        _,actual=read_csv(folder/name)
        if len(actual)!=len(wanted) or any(any(a.get(k,'')!=b.get(k,'') for k in set(a)|set(b)) for a,b in zip(actual,wanted)):raise ValueError('ROUND4_PRESENTATION_CHANGED:'+name)
    for n,sha in s['output_hashes'].items():
        if filehash(folder/n)!=sha:raise ValueError('ROUND4_PRESENTATION_SHA')
    cs=json.loads(old.unpack(core['summary.json']))
    for k in ('original_53_columns','all_retained_columns','tiered_coverage'):
        if s[k]!=cs[k]:raise ValueError('ROUND4_PRESENTATION_COVERAGE')
    return dict(version='round4-presentation-audit-v1',projects=len(expected[0]),columns=51,filled_cells=sum(bool(v) for r in expected[0] for v in r.values()),provenance_complete=True,preexisting_notes_preserved=True,output_hashes=s['output_hashes'],existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED')
