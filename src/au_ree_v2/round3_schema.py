"""Versioned 51-column projections with immutable, byte-reconstructable historical contracts."""
import base64,copy,gzip,hashlib,json,shutil
from pathlib import Path
from .round2_pipeline import read_csv,write_csv,write_json,FILES
from .blank_classification import classify_blanks,load_blank_rules
from .stage_rules import selected_mre
from .store import filehash,digest
RETIRED=('重算磁性元素-HTML磁性稀土_kt','預估年產重稀土_t_per_year')
CORE='census-project-summary-round3-v1'
PRESENTATION='census-project-summary-round3-presentation-v1'
ARCHIVE='retired_columns_trace.json'
LIMITATION='NOT_APPLICABLE_NO_MRE_IS_DENOMINATOR_CONVENTION_NOT_PROOF_OF_ABSENCE'

def config(repo):return json.loads((Path(repo)/'config/round3_coverage.json').read_text('utf8'))
def metric(n,d):return dict(filled=n,denominator=d,coverage=n/d if d else None)
def coverage(rows,trace,cfg):
    columns=list(rows[0]);resources=cfg['resource_columns'];other=cfg['nonresource_columns']
    if len(set(resources))!=len(resources) or len(set(other))!=len(other) or set(resources)&set(other) or set(resources)|set(other)!=set(columns) or set(RETIRED)&set(columns):raise ValueError('ROUND3_COVERAGE_PARTITION')
    first=[];second=[]
    for row in rows:
        status,_=selected_mre(row,trace)
        (second if status is False and row.get('總TREO蘊藏量_kt','')=='' else first).append(row)
    def count(rs,cols):return sum(r.get(c,'')!='' for r in rs for c in cols)
    extra=count(second,resources)
    a=metric(count(first,columns),len(first)*len(columns));a['rows']=len(first)
    b=metric(count(second,columns),len(second)*len(other)+extra);b.update(rows=len(second),base_denominator=len(second)*len(other),existing_filled_resource_cells=extra)
    filled=count(rows,columns)
    return dict(original_53_columns=metric(filled,len(rows)*53),all_retained_columns=metric(filled,len(rows)*len(columns)),tiered_coverage=dict(tier1=a,tier2=b,combined=metric(a['filled']+b['filled'],a['denominator']+b['denominator']),resource_columns=resources,nonresource_columns=other,limitation=LIMITATION,filled_resource_exception_convention='COUNT_IN_BOTH_NUMERATOR_AND_DENOMINATOR'))

def pack(folder,names):
    result={}
    for name in names:
        data=(Path(folder)/name).read_bytes()
        result[name]=dict(sha256=hashlib.sha256(data).hexdigest(),encoding='gzip-base64',data=base64.b64encode(gzip.compress(data,mtime=0)).decode('ascii'))
    return result

def unpack(record):
    if record['encoding']!='gzip-base64':raise ValueError('ROUND3_ARCHIVE_ENCODING')
    data=gzip.decompress(base64.b64decode(record['data'],validate=True))
    if hashlib.sha256(data).hexdigest()!=record['sha256']:raise ValueError('ROUND3_ARCHIVE_SHA')
    return data

def archive_csv(archive,name):
    import io,csv
    return list(csv.DictReader(io.StringIO(unpack(archive[name]).decode('utf-8-sig'))))

def verify_archive(folder,rows,trace):
    archive=json.loads((Path(folder)/ARCHIVE).read_text('utf8'))
    for record in archive['files'].values():unpack(record)
    original=archive_csv(archive['files'],'專案總表.csv');oldtrace=archive_csv(archive['files'],'field_provenance.csv')
    index={r['專案ID']:r for r in rows};p={(r['project_id'],r['column']):r for r in trace}
    if len(index)!=len(rows) or len({r['專案ID'] for r in original})!=len(original) or len(rows)!=len(original) or set(index)!={r['專案ID'] for r in original}:raise ValueError('ROUND3_COHORT_CHANGED')
    for row in original:
        for c,v in row.items():
            if c in RETIRED:
                if v:raise ValueError('ROUND3_RETIREMENT_LOST_VALUE')
            elif v and index[row['專案ID']].get(c)!=v:raise ValueError('ROUND3_EXISTING_VALUE_CHANGED')
    for old in oldtrace:
        if p.get((old['project_id'],old['column']))!=old:raise ValueError('ROUND3_EXISTING_PROVENANCE_CHANGED')
    if filehash(Path(folder)/'census_inventory.csv')!=archive['files']['census_inventory.csv']['sha256']:raise ValueError('ROUND3_INVENTORY_CHANGED')
    return {name:record['sha256'] for name,record in archive['files'].items()}

def audit(folder):
    folder=Path(folder);repo=Path(__file__).resolve().parents[2]
    summary=json.loads((folder/'summary.json').read_text('utf8'))
    columns,rows=read_csv(folder/'專案總表.csv');_,trace=read_csv(folder/'field_provenance.csv');_,missing=read_csv(folder/'missing_fields.csv')
    cfg=config(repo);expected=json.loads((repo/'config/project_summary_columns.json').read_text('utf8'))+['ASX代碼']
    presentation=summary['version']==PRESENTATION
    if presentation:expected=['總說明' if c=='元素數據一致性檢查' else c for c in expected]
    if len({r['專案ID'] for r in rows})!=len(rows):raise ValueError('ROUND3_DUPLICATE_PROJECT')
    if columns!=expected or summary['columns']!=51:raise ValueError('ROUND3_COLUMN_CONTRACT')
    values={(r['專案ID'],c):v for r in rows for c,v in r.items() if v}
    traces={(r['project_id'],r['column']):r for r in trace};gaps={(r['project_id'],r['column']) for r in missing}
    if len(traces)!=len(trace) or set(traces)!=set(values) or any(traces[k]['value']!=v for k,v in values.items()):raise ValueError('ROUND3_TRACE_MISMATCH')
    if len(gaps)!=len(missing) or gaps!={(r['專案ID'],c) for r in rows for c,v in r.items() if not v}:raise ValueError('ROUND3_GAPS_MISMATCH')
    for name,sha in summary['output_hashes'].items():
        if filehash(folder/name)!=sha:raise ValueError('ROUND3_OUTPUT_SHA')
    if not presentation:
        archive_hashes=verify_archive(folder,rows,trace)
        check=copy.deepcopy(missing);blank=classify_blanks(rows,check,trace,load_blank_rules(repo/'config/blank_classification.json'))
        if check!=missing or blank!=summary['blank_coverage']:raise ValueError('ROUND3_BLANK_CLASSIFICATION')
        cov=coverage(rows,trace,cfg)
        if any(summary.get(k)!=v for k,v in cov.items()):raise ValueError('ROUND3_COVERAGE')
    else:
        core=json.loads((folder/'presentation_core_trace.json').read_text('utf8'))
        for rec in core['files'].values():unpack(rec)
        original=archive_csv(core['files'],'專案總表.csv');original_trace=archive_csv(core['files'],'field_provenance.csv')
        source={r['專案ID']:r for r in original};frozen=json.loads((folder/ARCHIVE).read_text('utf8'))
        oldrows={r['專案ID']:r for r in archive_csv(frozen['presentation_files'],'專案總表.csv')}
        oldnotes={(r['project_id'],r['column']):r for r in archive_csv(frozen['presentation_files'],'field_provenance.csv') if r['column']=='總說明'}
        expectedtrace={(r['project_id'],r['column']):r for r in original_trace if r['column']!='元素數據一致性檢查'};expectedtrace.update(oldnotes)
        if traces!=expectedtrace:raise ValueError('ROUND3_PRESENTATION_PROVENANCE_CHANGED')
        for row in rows:
            for c,v in row.items():
                if v!=(oldrows[row['專案ID']][c] if c=='總說明' else source[row['專案ID']][c]):raise ValueError('ROUND3_PRESENTATION_VALUE_CHANGED')
        archive_hashes={n:r['sha256'] for n,r in core['files'].items()}
        cov=coverage(original,original_trace,cfg)
        if any(summary.get(k)!=v for k,v in cov.items()):raise ValueError('ROUND3_PRESENTATION_COVERAGE')
    return dict(version='round3-audit-v1',projects=len(rows),columns=len(columns),filled_cells=len(values),total_cells=len(rows)*len(columns),remaining_blank_cells=len(gaps),provenance_complete=True,missing_diagnostics_complete=True,output_hashes=summary['output_hashes'],reconstructed_historical_sha256=archive_hashes,existing_conclusion='INCOMPLETE/CONTINUE_UNCHANGED')

def write_projection(before,out,rows,trace,missing,repo,archive=None):
    before,out,repo=map(Path,(before,out,repo))
    if out.exists():raise ValueError('ROUND3_FRESH_OUTPUT_REQUIRED')
    out.mkdir(parents=True)
    columns=list(rows[0]);pf,_=read_csv(before/'field_provenance.csv');mf,_=read_csv(before/'missing_fields.csv')
    summary=json.loads((before/'summary.json').read_text('utf8'))
    blank=classify_blanks(rows,missing,trace,load_blank_rules(repo/'config/blank_classification.json'))
    for name,fields,records in [('專案總表.csv',columns,rows),('field_provenance.csv',pf,trace),('missing_fields.csv',mf,missing)]:write_csv(out/name,fields,records)
    shutil.copyfile(before/'census_inventory.csv',out/'census_inventory.csv')
    if archive is None:shutil.copyfile(before/ARCHIVE,out/ARCHIVE)
    else:write_json(out/ARCHIVE,archive)
    summary.update(version=CORE,columns=len(columns),columns_sha256=digest(columns),filled_counts={c:sum(bool(r[c]) for r in rows) for c in columns},blank_coverage=blank,**coverage(rows,trace,config(repo)))
    summary['output_hashes']={name:filehash(out/name) for name in (*FILES[:4],ARCHIVE)}
    write_json(out/'summary.json',summary);write_json(out/'audit.json',audit(out))

def migrate(before,out,repo):
    before,out,repo=map(Path,(before,out,repo));columns,rows=read_csv(before/'專案總表.csv');_,trace=read_csv(before/'field_provenance.csv');_,missing=read_csv(before/'missing_fields.csv')
    if len(columns)!=53 or any(r[c] for r in rows for c in RETIRED):raise ValueError('ROUND3_RETIREMENT_PRECONDITION')
    archive=dict(version='retired-columns-trace-v1',original_columns=columns,files=pack(before,FILES),presentation_files=pack(repo/'results/asx-current',('專案總表.csv','field_provenance.csv')),retired_columns=list(RETIRED),limitation=LIMITATION)
    old_missing=copy.deepcopy(missing);newrows=[{c:v for c,v in r.items() if c not in RETIRED} for r in rows]
    write_projection(before,out,newrows,trace,[m for m in missing if m['column'] not in RETIRED],repo,archive)
    _,updated=read_csv(out/'missing_fields.csv');g={(r['project_id'],r['column']):r for r in updated}
    changes=[]
    for m in old_missing:
        k=m['project_id'],m['column']
        if m['column'] in RETIRED:reason='EMPTY_COLUMN_RETIRED';new='REMOVED_COLUMN'
        elif (m.get('blank_class'),m.get('blank_rule_id'))!=(g[k].get('blank_class'),g[k].get('blank_rule_id')):reason=LIMITATION;new=g[k]['blank_class']
        else:continue
        changes.append(dict(project_id=k[0],column=k[1],old_value=m.get('blank_class',''),new_value=new,reason=reason))
    return [],changes,[]

def fill(before,out,fills,decisions,repo):
    _,rows=read_csv(Path(before)/'專案總表.csv');_,trace=read_csv(Path(before)/'field_provenance.csv');_,missing=read_csv(Path(before)/'missing_fields.csv')
    index={r['專案ID']:r for r in rows};pf=list(trace[0]);known={(p['project_id'],p['column']) for p in trace};approved={d['decision_id'] for d in decisions['decisions'] if d.get('decided_by')=='USER_EXPLICIT_APPROVAL'}
    for f in fills:
        k=f['project_id'],f['column']
        if k[0] not in index or k[1] not in index[k[0]] or index[k[0]][k[1]] or k in known or f['decision_id'] not in approved:raise ValueError('ROUND3_FILL_NOT_APPROVED_BLANK')
        p=dict.fromkeys(pf,'');p.update({k:v for k,v in f.get('provenance',{}).items() if k in p});p.update(project_id=k[0],column=k[1],value=str(f['value']))
        if not all(p.get(s) for s in ('source_sha256','locator','method')):raise ValueError('ROUND3_FILL_TRACE_REQUIRED')
        index[k[0]][k[1]]=p['value'];trace.append(p);known.add(k)
    keys={(f['project_id'],f['column']) for f in fills}
    write_projection(before,out,rows,trace,[m for m in missing if (m['project_id'],m['column']) not in keys],repo)
    from .coverage_task_audit import compare_projections
    return compare_projections(before,out)

def present(source,out,repo):
    source,out,repo=map(Path,(source,out,repo));audit(source)
    columns,rows=read_csv(source/'專案總表.csv');pf,trace=read_csv(source/'field_provenance.csv');mf,missing=read_csv(source/'missing_fields.csv')
    frozen=json.loads((source/ARCHIVE).read_text('utf8'));old={r['專案ID']:r for r in archive_csv(frozen['presentation_files'],'專案總表.csv')};notes=[r for r in archive_csv(frozen['presentation_files'],'field_provenance.csv') if r['column']=='總說明']
    replaced='元素數據一致性檢查';new='總說明';cols=[new if c==replaced else c for c in columns]
    output=[{new if c==replaced else c:old[r['專案ID']][new] if c==replaced else r[c] for c in columns} for r in rows]
    traces=[r for r in trace if r['column']!=replaced]+notes
    gaps=[r for r in missing if r['column']!=replaced]
    for r in output:
        if not r[new]:g=dict.fromkeys(mf,'');g.update(project_id=r['專案ID'],column=new,reason='NO_APPLICABLE_NOTE');gaps.append(g)
    if out.exists():raise ValueError('ROUND3_FRESH_PRESENTATION_REQUIRED')
    out.mkdir(parents=True)
    for name,fields,data in [('專案總表.csv',cols,output),('field_provenance.csv',pf,traces),('missing_fields.csv',mf,gaps)]:write_csv(out/name,fields,data)
    for name in ('census_inventory.csv',ARCHIVE):shutil.copyfile(source/name,out/name)
    write_json(out/'presentation_core_trace.json',dict(version='round3-presentation-core-v1',files=pack(source,FILES)))
    summary=json.loads((source/'summary.json').read_text('utf8'));summary.update(version=PRESENTATION,presentation_note_policy='PRESERVE_PREEXISTING_VALUES_AND_PROVENANCE_NO_REFRESH',columns_sha256=digest(cols),filled_counts={c:sum(bool(r[c]) for r in output) for c in cols})
    summary['output_hashes']={n:filehash(out/n) for n in (*FILES[:4],ARCHIVE,'presentation_core_trace.json')}
    write_json(out/'summary.json',summary);write_json(out/'audit.json',audit(out))
