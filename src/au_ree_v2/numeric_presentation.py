"""Opt-in reversible decimal presentation for source-bound HM oxide derivations.

Only binary round-off is removed. Source rounding intervals and canonical values
are not revised, and this does not assert additional significant figures.
"""
import copy, json, math, re, shutil, tempfile
from decimal import Decimal
from pathlib import Path
from .round2_pipeline import read_csv, write_csv, write_json
from .store import filehash

VERSION = 'round3-source-decimal-presentation-v1'
ARCHIVE = 'numeric_presentation_original.json'
TRACE = 'numeric_presentation_changes.json'
METHOD = 'EXACT_SOURCE_DECIMAL_ARITHMETIC_BINARY_TAIL_ONLY'

def token(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',value):
        raise ValueError('NUMERIC_PRESENTATION_SOURCE_TOKEN')
    return Decimal(value)

def text(value):
    return format(value,'f').rstrip('0').rstrip('.') if '.' in format(value,'f') else format(value,'f')

def exact_hm_values(review, columns):
    from .project_summary import ELEMENTS, MAGNET, HEAVY
    mode=review.get('partial_resource_projection',{})
    if mode.get('mode')!='BULK_ORE_AND_HM_HOSTED_OXIDES_ONLY':return {}
    mass=mode['mass_inputs']['hm_mass_mt']
    if mass['unit']!='Mt':raise ValueError('NUMERIC_PRESENTATION_HM_UNIT')
    hm=token(mass['original_token'])
    if hm!=Decimal(str(mass['value'])) or hm<=0:raise ValueError('NUMERIC_PRESENTATION_HM_VALUE')
    elements={}
    for obs in review['observations']:
        if obs.get('original_unit')!='%HM':continue
        basis=obs.get('basis')
        if basis not in ELEMENTS or basis in elements:raise ValueError('NUMERIC_PRESENTATION_OXIDE_BASIS')
        pct=token(obs['original_token'])
        if not 0<=pct<=100:raise ValueError('NUMERIC_PRESENTATION_PERCENT')
        elements[basis]=hm*pct*Decimal(10)
    values={}
    for el,value in elements.items():
        matches=[c for c in columns if c.startswith(el+'_氧化') and c.endswith('_kt')]
        if len(matches)!=1:raise ValueError('NUMERIC_PRESENTATION_COLUMN')
        values[matches[0]]=value
    for col,needed in [('NdPr蘊藏量_kt_需兩者皆公布',('Nd2O3','Pr6O11')),('完整重稀土組合蘊藏量_kt_需8元素皆公布',HEAVY),('磁性元素重算值_NdPrTbDy_kt',MAGNET)]:
        if all(e in elements for e in needed):values[col]=sum((elements[e] for e in needed),Decimal(0))
    if elements:values['已公布元素總和_kt']=sum(elements.values(),Decimal(0))
    return values

def derive(rows,trace,reviews):
    rows=copy.deepcopy(rows);trace=copy.deepcopy(trace)
    index={r['專案ID']:r for r in rows}; prov={(r['project_id'],r['column']):r for r in trace}; changes=[]
    seen=set()
    for review in reviews:
        project=review.get('project_id');row=index.get(project)
        if row is None:continue
        exact=exact_hm_values(review,list(row))
        for column,value in exact.items():
            key=(project,column);p=prov.get(key);old=row.get(column,'')
            if not old or p is None:continue
            if (review['review_id'] not in json.loads(p.get('review_ids') or '[]') or p.get('source_sha256')!=review['source_sha256'] or p.get('scope')!=review['scope'] or p.get('effective_date')!=review['effective_date']):continue
            if key in seen:raise ValueError('NUMERIC_PRESENTATION_AMBIGUOUS_REVIEW')
            seen.add(key)
            original=Decimal(old)
            if not original.is_finite():raise ValueError('NUMERIC_PRESENTATION_NONFINITE')
            # No arbitrary rounding: retain real differences; change only binary noise.
            if original==value:continue
            allowed=Decimal(str(math.ulp(float(value))))*4
            if abs(original-value)>allowed:raise ValueError('NUMERIC_PRESENTATION_NOT_BINARY_TAIL')
            new=text(value)
            changes.append(dict(project_id=project,column=column,old_value=old,new_value=new,
                method=METHOD,source_sha256=review['source_sha256'],review_id=review['review_id'],
                statement_id=review['statement_id'],source_scope=review['scope'],
                original_provenance=copy.deepcopy(p),maximum_difference_kt=str(allowed),
                source_decimal_inputs=dict(hm_mass=copy.deepcopy(review['partial_resource_projection']['mass_inputs']['hm_mass_mt']),oxides=[dict(basis=o['basis'],original_token=o['original_token'],original_unit=o['original_unit'],rounding_half_width=o.get('rounding_half_width')) for o in review['observations'] if o.get('original_unit')=='%HM']),
                limitation='Display-only exact arithmetic; original source rounding uncertainty remains.'))
            row[column]=new;p['value']=new
    return rows,trace,changes

def present(source,out,repo):
    from . import round3_schema as schema
    source,out,repo=map(Path,(source,out,repo))
    original_summary=json.loads((source/'summary.json').read_text('utf8'))
    if original_summary['version']!=schema.PRESENTATION:raise ValueError('NUMERIC_PRESENTATION_INPUT_VERSION')
    schema.audit(source)
    if out.exists():raise ValueError('NUMERIC_PRESENTATION_FRESH_OUTPUT')
    columns,rows=read_csv(source/'專案總表.csv');pf,trace=read_csv(source/'field_provenance.csv')
    review_bytes=(repo/'config/asx_source_reviews.json').read_bytes()
    reviews=json.loads(review_bytes)['reviews'];newrows,newtrace,changes=derive(rows,trace,reviews)
    shutil.copytree(source,out)
    write_json(out/ARCHIVE,dict(version=VERSION,files=schema.pack(source,[p.name for p in sorted(source.iterdir()) if p.is_file()]),source_reviews_sha256=filehash(repo/'config/asx_source_reviews.json')))
    write_json(out/TRACE,dict(version=VERSION,method=METHOD,changes=changes,new_cells=0,precision_policy='REMOVE_BINARY_TAIL_ONLY_NOT_REESTIMATE_SOURCE_UNCERTAINTY'))
    write_csv(out/'專案總表.csv',columns,newrows);write_csv(out/'field_provenance.csv',pf,newtrace)
    summary=copy.deepcopy(original_summary);summary['version']=VERSION
    summary['numeric_presentation']=dict(method=METHOD,changed_display_cells=len(changes),new_cells=0,core_values_preserved=True)
    summary['output_hashes']={n:filehash(out/n) for n in (*original_summary['output_hashes'],ARCHIVE,TRACE)}
    write_json(out/'summary.json',summary)
    metadata(source,out,summary,changes)
    result=audit(out,repo);write_json(out/'audit.json',result)
    return result

def metadata(original,out,summary,changes):
    validation=dict(version=VERSION,original_publication_validation_sha256=filehash(original/'validation.json'),
        presentation_output_hashes=summary['output_hashes'],changed_display_cells=len(changes),new_cells=0,
        canonical_evidence_unchanged=True,original_validation_location=ARCHIVE)
    write_json(out/'validation.json',validation)
    status=json.loads((original/'publication_status.json').read_text('utf8'))
    status['numeric_presentation']=dict(version=VERSION,new_cells=0,changed_display_cells=len(changes),original_publication_status_location=ARCHIVE)
    write_json(out/'publication_status.json',status)
    note='\n\n## 十進位呈現修正\n\n僅移除已核實 HM 衍生量的二進位浮點尾數；不增加資料格，不改原始來源精度或不確定性。完整原值、原 provenance 與發布驗收保存在 numeric_presentation_original.json；本次逐格差異在 numeric_presentation_changes.json。核心證據表與歷史結果不變。\n'
    (out/'README.md').write_text((original/'README.md').read_text('utf8')+note,encoding='utf8')

def audit(folder,repo=None):
    from . import round3_schema as schema
    folder=Path(folder);repo=Path(repo) if repo else Path(__file__).resolve().parents[2]
    archive=json.loads((folder/ARCHIVE).read_text('utf8'))
    if archive['source_reviews_sha256']!=filehash(repo/'config/asx_source_reviews.json'):raise ValueError('NUMERIC_PRESENTATION_REVIEW_SHA')
    with tempfile.TemporaryDirectory(prefix='au-ree-decimal-audit-') as directory:
        original=Path(directory)
        for name,record in archive['files'].items():
            if Path(name).name!=name:raise ValueError('NUMERIC_PRESENTATION_ARCHIVE_PATH')
            (original/name).write_bytes(schema.unpack(record))
        core_audit=schema.audit(original)
        columns,rows=read_csv(original/'專案總表.csv');pf,trace=read_csv(original/'field_provenance.csv')
        reviews=json.loads((repo/'config/asx_source_reviews.json').read_text('utf8'))['reviews']
        newrows,newtrace,changes=derive(rows,trace,reviews)
        if read_csv(folder/'專案總表.csv')!=(columns,newrows) or read_csv(folder/'field_provenance.csv')!=(pf,newtrace):raise ValueError('NUMERIC_PRESENTATION_VALUES')
        record=json.loads((folder/TRACE).read_text('utf8'))
        if record!=dict(version=VERSION,method=METHOD,changes=changes,new_cells=0,precision_policy='REMOVE_BINARY_TAIL_ONLY_NOT_REESTIMATE_SOURCE_UNCERTAINTY'):raise ValueError('NUMERIC_PRESENTATION_TRACE')
        summary=json.loads((folder/'summary.json').read_text('utf8'))
        expected=json.loads((original/'summary.json').read_text('utf8'));expected['version']=VERSION
        expected['numeric_presentation']=dict(method=METHOD,changed_display_cells=len(changes),new_cells=0,core_values_preserved=True)
        expected['output_hashes']={n:filehash(folder/n) for n in (*expected['output_hashes'],ARCHIVE,TRACE)}
        if summary!=expected:raise ValueError('NUMERIC_PRESENTATION_SUMMARY')
        expected_metadata=original/'metadata';expected_metadata.mkdir()
        metadata(original,expected_metadata,summary,changes)
        for name in ('validation.json','publication_status.json','README.md'):
            if (folder/name).read_bytes()!=(expected_metadata/name).read_bytes():raise ValueError('NUMERIC_PRESENTATION_METADATA')
        for name,rec in archive['files'].items():
            if name not in ('專案總表.csv','field_provenance.csv','summary.json','audit.json','validation.json','publication_status.json','README.md') and filehash(folder/name)!=rec['sha256']:raise ValueError('NUMERIC_PRESENTATION_UNRELATED_CHANGE')
        result=copy.deepcopy(core_audit);result.update(version=VERSION,output_hashes=summary['output_hashes'],changed_display_cells=len(changes),new_cells=0,original_presentation_hashes={n:r['sha256'] for n,r in archive['files'].items()})
        return result
