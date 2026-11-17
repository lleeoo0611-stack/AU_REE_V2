"""Accept exactly one new CI build against immutable published reference cells."""
import csv,hashlib,json,re,shutil,subprocess,zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from decimal import Decimal,InvalidOperation,localcontext
from pathlib import Path,PurePosixPath
from urllib.parse import urlsplit
from au_ree_v2.store import digest
from au_ree_v2.security import public_export,sensitive_reference

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'work/claims-ci-v8'
BASE=ROOT/'results/claims-locators-2026-11-16'
OUT=BASE/'v8'
FINAL=OUT/'ci'
csv.field_size_limit(16*1024*1024)
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(name,value):(FINAL/name).write_text(json.dumps(public_export(value),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def write(name,rows,headers):
    with (FINAL/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,headers);w.writeheader();w.writerows(public_export(rows))
def equal(expected,actual):
    if expected==actual:return True
    try:
        a,b=Decimal(expected),Decimal(actual)
        with localcontext() as context:
            context.prec=80
            return a.is_finite() and b.is_finite() and a==b.quantize(Decimal(1).scaleb(a.as_tuple().exponent))
    except InvalidOperation:return False

run=load(WORK/'api-run.json');jobs=load(WORK/'api-jobs.json')['jobs'];meta=load(WORK/'api-artifact.json')
commit=(WORK/'expected-commit.txt').read_text().strip()
assert run['head_sha']==commit and run['status']=='completed' and run['conclusion']=='success'
job=next(j for j in jobs if j['name']=='automated-build')
assert job['conclusion']=='success'
for name in ('Verify checkout begins without work data','Build only from approved public registry','Unit regressions with XML','R analytical regressions','Assert originals and frozen history unchanged'):
    assert next(s for s in job['steps'] if s['name']==name)['conclusion']=='success',name
archive=WORK/'artifact.zip';archive_sha=hashlib.sha256(archive.read_bytes()).hexdigest()
assert meta.get('digest') in (None,'sha256:'+archive_sha)
artifact=WORK/'artifact';assert not artifact.exists()
artifact.mkdir();index=[]
with zipfile.ZipFile(archive) as z:
    assert sum(i.file_size for i in z.infolist())<=256*1024*1024
    for entry in z.infolist():
        if entry.is_dir():continue
        relative=PurePosixPath(entry.filename)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert relative.suffix.lower() not in ('.pdf','.xlsx','.deb','.traineddata')
        target=artifact/relative
        if entry.filename.startswith('work/test-xml/'):
            target=artifact/'work/test-xml'/(hashlib.sha256(entry.filename.encode()).hexdigest()[:16]+'.xml')
        assert target.resolve().is_relative_to(artifact.resolve())
        target.parent.mkdir(parents=True,exist_ok=True);raw=z.read(entry);target.write_bytes(raw)
        index.append(dict(path=entry.filename,sha256=hashlib.sha256(raw).hexdigest()))
clean=artifact/'work/clean';network=load(clean/'network_status.json')
assert network['valid_for_delivery'] and network['status']=='NETWORK_VALID'
log=(artifact/'work/clean-build.log').read_text(encoding='utf8');completed=[]
for match in re.finditer(r'(?m)^\{',log):
    try:value,_=json.JSONDecoder().raw_decode(log[match.start():])
    except ValueError:continue
    if isinstance(value,dict) and value.get('output_dir') and value.get('run_id'):completed.append(value)
assert len(completed)==1
latest=completed[0];folders=list(clean.glob('runs/*/project-summary'));assert len(folders)==1
summary=folders[0];output=summary.parent;assert output.name==latest['run_id']
configuration=load(output/'configuration.json')
assert digest(configuration)==latest['configuration_sha256']
assert configuration['claims_sha256']==hashlib.sha256(subprocess.check_output(['git','show',commit+':data/claims.json'],cwd=ROOT)).hexdigest()
assert configuration['sources']==json.loads(subprocess.check_output(['git','show',commit+':config/sources.json'],cwd=ROOT))
code=digest({p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for p in sorted([*ROOT.glob('src/**/*.py'),*ROOT.glob('R/*.R')])})
assert latest['code']['content_sha256']==code
snapshots=load(output/'snapshot_lock.json');receipts=read(output/'acquisition_report.csv')
by_key={r['key']:r for r in receipts}
verified={s['sha256']:s for s in snapshots if by_key.get(s['key'],{}).get('sha_match')=='True' and by_key[s['key']]['status'] in ('FETCHED_SHA_VERIFIED','COMMITTED_SNAPSHOT_SAME_SHA','COMMITTED_MANAGED_SAME_SHA','SNAPSHOT_FALLBACK_SAME_SHA','ALTERNATE_SAME_SHA')}
known_sources=configuration['sources']['sources']+load(ROOT/'data/manifest.json')['snapshots']
known_keys={s['key'] for s in known_sources}
known_urls={s.get('url') for s in known_sources}
values={r['專案ID']:r for r in read(summary/'專案總表.csv')}
trace={(r['project_id'],r['column']):r for r in read(summary/'field_provenance.csv')}
missing={(r['project_id'],r['column']):r for r in read(summary/'missing_fields.csv')}
stage=read(summary/'stage_rule_audit.csv')
# Audit the same CI receipt set before the fixed-cell acceptance gate.
FINAL.mkdir(exist_ok=True)
write('acquisition_report.csv',receipts,list(receipts[0]))
stopped_rows=[r for r in receipts if r['status']=='HOST_STOPPED']
host_audit=[]
for host in sorted({r['host'] for r in stopped_rows}):
    affected=[r for r in stopped_rows if r['host']==host]
    reasons=sorted({r['stop_reason'] for r in affected})
    attempts=[a for r in receipts if r['host']==host for a in json.loads(r.get('http_attempts') or '[]')]
    host_audit.append(dict(host=host,affected_sources=len(affected),stop_reasons=json.dumps(reasons),
                           http_statuses=json.dumps([a.get('http_status') for a in attempts]),
                           stopped_by_404=any(re.search(r'HOST_STOPPED:404(?:$|[;\s])',reason) for reason in reasons)))
write('host_stops.csv',host_audit,['host','affected_sources','stop_reasons','http_statuses','stopped_by_404'])
if any(row['stopped_by_404'] for row in host_audit):
    save('acceptance.json',dict(status='STOP_HOST_STOPPED_BY_404',run_id=run['id'],run_url=run['html_url']))
    raise SystemExit('STOP: host stopped by 404; no rerun')

reference=BASE/'baseline_reference_609.csv'
assert hashlib.sha256(reference.read_bytes()).hexdigest()=='02acc91760c8774f7377d12f2a428d1a1d6b6fba6f1620237e267101cdb0ff4e'
guard=[]
for cell in read(reference):
    key=cell['project_id'],cell['column'];value=values.get(key[0],{}).get(key[1],'');ok=equal(cell['reference_value'],value)
    ft=trace.get(key,{})
    blockers=[r for r in stage if r['project_id']==key[0] and r.get('reason')] if not ok else []
    guard.append(dict(project_id=key[0],column=key[1],reference_value=cell['reference_value'],ci_value=value,
        status='SAME' if ok else 'FORMAL_MISSING' if not value else 'DIFFERENT',
        reason=missing.get(key,{}).get('reason','' if ok else 'FORMAL_VALUE_CHANGED'),
        missing_details=missing.get(key,{}).get('details',''),source_sha256=ft.get('source_sha256',''),
        source_url=ft.get('source_url',''),locator=ft.get('locator',''),
        stage_blockers=json.dumps(blockers,ensure_ascii=False,separators=(',',':'))))
assert len(guard)==609
lost=[r for r in guard if r['status']!='SAME'];FINAL.mkdir(exist_ok=True)
write('ci_609_guard.csv',guard,list(guard[0]));write('ci_609_losses.csv',lost,list(guard[0]))
if lost:
    save('acceptance.json',dict(status='STOP_609_GUARD_FAILED',run_id=run['id'],run_url=run['html_url'],protected_preserved=609-len(lost),lost=lost,target_statuses={}))
    raise SystemExit('STOP: fixed 609 cells lost; no further acceptance work')
old_rows=read(BASE/'v6/ci/cell_comparison.csv')
vic=next(s for s in configuration['sources']['sources'] if s['key']=='reviewed_source_31a205168b6ae647')
comparison=[];increments=[]
for old in old_rows:
    key=old['project_id'],old['column'];expected=old['experiment_value'];value=values.get(key[0],{}).get(key[1],'');ft=trace.get(key,{})
    if old['status']=='KNOWN_STRUCTURAL_DIFFERENCE' and not expected:status,reason=old['status'],old['reason']
    elif expected and not value:status,reason='FORMAL_MISSING',missing.get(key,{}).get('reason','NO_FORMAL_CELL')
    elif not expected and value:status,reason='FORMAL_ONLY','FORMAL_VALUE_NOT_PRESENT_IN_PUBLISHED_REFERENCE'
    elif equal(expected,value):status,reason='SAME','EXACT_VALUE' if expected==value else 'REFERENCE_PRESENTATION_PRECISION'
    else:
        status,reason='DIFFERENT','SOURCE_OR_RULE_OUTPUT_DIFFERS_REVIEW_REQUIRED'
        source=verified.get(ft.get('source_sha256',''));name_column=key[1]=='資料來源名稱'
        reference_assets=[s for s in known_sources if (s.get('source_sha256') or s.get('sha256'))==old['experiment_source_sha256'] and s.get('url')==old['experiment_source_url']]
        reference_known=expected in (known_keys if name_column else known_urls) or (name_column and bool(reference_assets)) or (not name_column and expected==old['experiment_source_url'])
        if key[1] in ('資料來源名稱','資料來源URL') and reference_known and source and value==source['key' if name_column else 'url']:
            status,reason='KNOWN_STRUCTURAL_DIFFERENCE','FORMAL_RECORDS_VERIFIED_SOURCE'
        elif key[1] in ('緯度','經度') or re.search(r'_(?:kt|pct|Mt|共15項)$',key[1]):
            try:
                a,b=Decimal(expected),Decimal(value)
                with localcontext() as context:
                    context.prec=80
                    if a.is_finite() and b.is_finite() and a!=b and abs(a-b)<=max(abs(a),abs(b))*Decimal('1e-12'):
                        status,reason='NUMERIC_TOLERANCE_SAME','RELATIVE_TOLERANCE_1E_12_NOT_COUNTED_AS_SAME'
            except InvalidOperation:pass
    row=dict(old,formal_value=value,status=status,reason=reason,formal_source_sha256=ft.get('source_sha256',''),formal_source_url=ft.get('source_url',''),formal_locator=ft.get('locator',''),formal_method=ft.get('method',''))
    comparison.append(row)
    if key[1]!='專案ID' and expected and status=='SAME' and old['status']!='SAME':
        category='ACDC_HM_SPECIES_AND_MASS' if key[0]=='AU-447261eed0e81eae88bf' else 'OTHER'
        increments.append(dict(project_id=key[0],column=key[1],previous_status=old['status'],new_status=status,attribution=category,source_sha256=ft.get('source_sha256','')))
write('cell_comparison.csv',comparison,list(comparison[0]))
write('same_increments.csv',increments,['project_id','column','previous_status','new_status','attribution','source_sha256'])
remaining=[]
for row in comparison:
    if row['status']!='DIFFERENT':continue
    page=re.search(r'(?i)\bp(?:age)?\s*(\d+)\b',row['experiment_locator'])
    remaining.append(dict(row,reference_pdf_page=page.group(1) if page else '',formal_pdf_page=trace.get((row['project_id'],row['column']),{}).get('pdf_page','')))
write('remaining_differences.csv',remaining,list(comparison[0])+['reference_pdf_page','formal_pdf_page'])
for name in ('專案總表.csv','field_provenance.csv','missing_fields.csv','coverage.json','stage_rule_audit.csv'):
    shutil.copy2(summary/name,FINAL/name)
write('acquisition_report.csv',receipts,list(receipts[0]))
for name in ('fallback_report.csv','asx_probe.csv','dns_preflight.csv','robots_403_hosts.csv'):
    if (clean/name).exists():
        recorded=read(clean/name)
        if recorded:write(name,recorded,list(recorded[0]))
save('network_status.json',network);save('artifact_index.json',index)
acdc_id='AU-447261eed0e81eae88bf'
acdc=[r for r in comparison if r['project_id']==acdc_id]
write('acdc_fields.csv',acdc,list(comparison[0]))
oxide_names=('La2O3','CeO2','Pr6O11','Nd2O3','Sm2O3','Eu2O3','Gd2O3','Tb4O7','Dy2O3','Ho2O3','Er2O3','Tm2O3','Yb2O3','Lu2O3','Y2O3')
oxides=[r for r in acdc if any(r['column'].startswith(name+'_') for name in oxide_names)]
assert len(oxides)==15
write('acdc_15_oxides.csv',oxides,list(comparison[0]))
has_contract=all(r['formal_value'] for r in oxides)
save('acdc_summary.json',dict(project_id=acdc_id,contract_applied=has_contract,contract_status='HM_CONTRACT_VALIDATED_IN_CI' if has_contract else 'HM_CONTRACT_NOT_ESTABLISHED',
    summary_before=next(r['formal_value'] for r in old_rows if r['project_id']==acdc_id and r['column']=='總說明'),
    summary_ci=values.get(acdc_id,{}).get('總說明',''),oxide_cells_with_values=sum(bool(r['formal_value']) for r in oxides),
    source_sha_updated=False,claims_updated=True,new_same_cells=[r for r in increments if r['project_id']==acdc_id]))
python_totals=Counter(tests=0,failures=0,errors=0,skipped=0);r_totals=None
for path in (artifact/'work/test-xml').glob('*.xml'):
    element=ET.parse(path).getroot()
    for suite in [element] if element.tag=='testsuite' else element.findall('testsuite'):
        totals={key:int(suite.get(key,0)) for key in python_totals}
        if suite.get('name')=='R analytical regression script':r_totals=totals
        else:python_totals.update(totals)
assert python_totals==dict(tests=452,failures=0,errors=0,skipped=0),python_totals
assert r_totals==dict(tests=1,failures=0,errors=0,skipped=0)
target=[r for r in comparison if r['column']!='專案ID' and r['experiment_value']];assert len(target)==2101
statuses=dict(Counter(r['status'] for r in target));old_statuses=Counter(r['status'] for r in old_rows if r['column']!='專案ID' and r['experiment_value'])
lost_other=[r for r in comparison if r['column']!='專案ID' and r['experiment_value'] and r['status']!='SAME' and next(o['status'] for o in old_rows if o['project_id']==r['project_id'] and o['column']==r['column'])=='SAME']
write('v6_nonprotected_same_losses.csv',lost_other,list(comparison[0]))
missing_counts=Counter(r['reason'] for r in target if r['status']=='FORMAL_MISSING')
write('missing_reason_counts.csv',[dict(reason=k,count=v) for k,v in missing_counts.items()],['reason','count'])


old_by_cell={(r['project_id'],r['column']):r for r in old_rows}
other_changes=[]
for row in comparison:
    old=old_by_cell[row['project_id'],row['column']]
    if row['project_id']==acdc_id or all(row[k]==old[k] for k in ('formal_value','status','reason')):continue
    kind='FORMAL_VALUE_CHANGED' if row['formal_value']!=old['formal_value'] else 'CLASSIFICATION_OR_REASON_CHANGED'
    other_changes.append(dict(row,baseline_formal_value=old['formal_value'],baseline_status=old['status'],
        baseline_reason=old['reason'],difference_type=kind,
        change_explanation=missing.get((row['project_id'],row['column']),{}).get('details',row['reason'])))
write('other_project_changes.csv',other_changes,list(comparison[0])+['baseline_formal_value','baseline_status','baseline_reason','difference_type','change_explanation'])
partial_ids={'AU-ff758cad5beb276d327d','AU-574465211976ec57b1ef'}
partial_changes=[r for r in other_changes if r['project_id'] in partial_ids]
save('partial_project_regression.json',dict(status='UNCHANGED' if not partial_changes else 'STOP_CHANGED',projects=sorted(partial_ids),columns_per_project=51,changes=partial_changes))
acdc_changes=[r for r in comparison if r['project_id']==acdc_id and r['formal_value']!=next(o['formal_value'] for o in old_rows if o['project_id']==r['project_id'] and o['column']==r['column'])]
write('acdc_all_changes.csv',acdc_changes,list(comparison[0]))
if not has_contract:
    save('acceptance.json',dict(status='STOP_ACDC_CONTRACT_NOT_ESTABLISHED',run_id=run['id'],run_url=run['html_url'],commit=commit,protected_preserved=609,lost=0,target_statuses=statuses))
    raise SystemExit('STOP: ACDC fifteen oxide fields not all available; no valid HM contract asserted')
diagnostic=read(BASE/'v7/acdc_hm_diagnostic.csv')
hm_values=[]
for component in diagnostic:
    record=next(r for r in oxides if r['column'].startswith(component['oxide']+'_'))
    assert Decimal(record['formal_value'])==Decimal(component['hm_side_kt']),component['oxide']
    note='REFERENCE_PAGE3_ROUNDED_BULK_PPM;DIFFERENT_RETAINED' if component['oxide']=='Tb4O7' else ''
    hm_values.append(dict(component,ci_value_kt=record['formal_value'],reference_value_kt=record['experiment_value'],
        comparison_status=record['status'],comparison_reason=record['reason'],known_difference_note=note))
write('acdc_hm_values.csv',hm_values,list(hm_values[0]))
vic_ids={b['project_id'] for b in vic['summary_tenements']}
vic_rows=[dict(r,coordinate_reason=missing.get((r['project_id'],r['column']),{}).get('reason',''))
    for r in comparison if r['project_id'] in vic_ids and r['column'] in ('經度','緯度')]
assert len(vic_rows)==8 and all(not r['formal_value'] and r['coordinate_reason']=='SOURCE_AFTER_CUTOFF' for r in vic_rows)
write('known_limit_vic_coordinates.csv',vic_rows,list(comparison[0])+['coordinate_reason'])
save('acceptance.json',dict(status='CI_609_PRESERVED_AWAITING_RESEARCHER_REVIEW',run_id=run['id'],run_url=run['html_url'],commit=commit,
    job_id=job['id'],artifact_id=meta['id'],artifact_sha256=archive_sha,protected_preserved=609,lost=0,
    target_statuses=statuses,status_delta={k:statuses.get(k,0)-v for k,v in old_statuses.items()},
    same_increment_categories=dict(Counter(r['attribution'] for r in increments)),new_same_cells=len(increments),
    nonprotected_v6_same_losses=len(lost_other),net_same_increment=statuses.get('SAME',0)-876,
    gap_to_2101=2101-statuses.get('SAME',0),missing_reasons=dict(missing_counts),other_project_changes=len(other_changes),
    acdc_contract_applied=True,python_tests=dict(python_totals),r_tests=r_totals,code_content_sha256=code,configuration_sha256=latest['configuration_sha256']))
print(json.dumps(dict(status='CI_609_PRESERVED',target_statuses=statuses,increments=dict(Counter(r['attribution'] for r in increments)),same_losses=len(lost_other),other_project_changes=len(other_changes)),ensure_ascii=False,indent=2))
