"""Explicit basis and scope checks, no inference of independent approval."""
import json
import math
import re
from pathlib import Path
from .store import canonical, digest, entity, issue
from .census import ingest_workbook
from .official import ingest_official_table, ingest_prospectus
from .national import ingest_legacy_e1
from .screen_index import ingest as ingest_screen_index


def html_text(root, source):
    """Decode an advertised static article payload without executing JavaScript."""
    from html.parser import HTMLParser
    text = (Path(root)/source['path']).read_text(encoding='utf-8')
    if source.get('text_contract') == 'LSE_ARTICLE_BODY_JS_STRING_V1':
        payload = re.findall(r'var articleBody="((?:\\.|[^"\\])*)";', text)
        if len(payload) != 1:
            raise ValueError('ARTICLE_BODY_MISSING_OR_AMBIGUOUS')
        encoded = re.sub(r'\\x([0-9a-fA-F]{2})', r'\\u00\1', payload[0])
        text = json.loads('"'+encoded+'"')
        text = re.sub(r'<(script|style)\b[^>]*>.*?</\1\s*>', '', text, flags=re.I|re.S)
    class Text(HTMLParser):
        def __init__(self):super().__init__();self.parts=[]
        def handle_data(self,value):self.parts.append(value)
    parser=Text();parser.feed(text)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts))


def validate_pages(root, source, evidence, snapshots, cache=None):
    """One hash/page/marker contract for event and engineering evidence.

    Existing selective extraction artifacts remain SHA-bound; no OCR is run
    implicitly while interpreting a financial or engineering observation.
    """
    from .selection import source_check
    from pypdf import PdfReader
    root = Path(root)
    cache = cache if cache is not None else {}
    key = ('hash', source['sha256'])
    if key not in cache:
        cache[key] = source_check(source, '9999-12-31', root)
    if cache[key]:
        raise ValueError(cache[key])
    if evidence['source_sha256'] != source['sha256']:
        raise ValueError('EXTRACTION_VERSION_MISMATCH')
    if source['kind'] == 'html':
        markers=evidence.get('source_markers')
        if not markers or not all(m in html_text(root,source) for m in markers):
            raise ValueError('EXTRACTION_HTML_MARKER_CHECK_FAILED')
        return
    bindings = [dict(page=evidence['pdf_page'], markers=evidence['page_markers'])]
    bindings += evidence.get('context_evidence', [])
    if evidence.get('finance_evidence'):
        bindings.append(evidence['finance_evidence'])
    for binding in bindings:
        page = binding['page']
        if not isinstance(page, int) or page < 1 or not binding['markers']:
            raise ValueError('MISSING_PHYSICAL_PAGE_OR_MARKERS')
        key = (source['sha256'], page)
        if key not in cache:
            import pypdf
            contract=dict(source_sha256=source['sha256'],page=page,parser='pypdf-'+pypdf.__version__,parameters='extract_text-default-v1')
            import os
            cache_root=Path(os.environ.get('AU_REE_NATIVE_CACHE',str(root/'work/cache/native_pages')))
            cached_path=cache_root/(digest(contract)+'.json')
            payload=None
            if cached_path.exists():
                try:
                    candidate=json.loads(cached_path.read_text(encoding='utf8'))
                    if candidate['contract']==contract and candidate['text_sha256']==digest(candidate['text']):payload=candidate
                except (KeyError,ValueError,OSError):pass
            if payload is None:
                reader_key = ('reader', source['sha256'])
                if reader_key not in cache:cache[reader_key] = PdfReader(root/source['path'])
                text=cache[reader_key].pages[page-1].extract_text() or ''
                payload=dict(contract=contract,text=text,text_sha256=digest(text))
                cached_path.parent.mkdir(parents=True,exist_ok=True)
                cached_path.write_text(canonical(payload)+'\n',encoding='utf8')
            cache[key]=payload['text']
        text = cache[key]
        if evidence.get('page_extraction_key') and page == evidence['pdf_page']:
            artifact = next(s for s in snapshots if s['key'] == evidence['page_extraction_key'])
            if artifact['sha256'] != evidence['page_extraction_sha256']:
                raise ValueError('PAGE_ARTIFACT_VERSION_MISMATCH')
            data = json.loads((root/artifact['path']).read_text(encoding='utf-8'))
            if data['source_sha256'] != source['sha256'] or data['physical_page'] != page or data['status'] != 'EXTRACTED_REQUIRES_SCOPE_VALIDATION':
                raise ValueError('PAGE_ARTIFACT_BINDING_FAILED')
            text = data['text']
        if evidence.get('kind')=='SOURCE_BOUND_SCIENTIFIC_CLAIM' and page==evidence['pdf_page']:
            if ' '.join(evidence['raw_text'].split()) not in ' '.join(text.split()):raise ValueError('SCIENTIFIC_QUOTE_NOT_BOUND_TO_PAGE')
        if not all(marker in text for marker in binding['markers']):
            raise ValueError('EXTRACTION_PAGE_CHECK_FAILED')


def load_claims(root, expected_sha=None, freeze=False):
    """Resolve the existing configuration's immutable extraction contract.

    Source PDFs alone cannot freeze later transcriptions of those same pages.
    Old configurations already record this SHA; never substitute live claims
    when reconstructing a historical result.
    """
    from .store import filehash
    root=Path(root);live=root/'data/claims.json'
    sha=expected_sha or filehash(live)
    archive=root/'data/snapshots'/(sha+'.claims.json')
    path=live if filehash(live)==sha else archive
    if not path.exists() or filehash(path)!=sha:
        raise ValueError('FROZEN_CLAIMS_UNAVAILABLE_OR_HASH_MISMATCH: '+sha)
    if freeze:
        if not archive.exists():archive.write_bytes(path.read_bytes())
        if filehash(archive)!=sha:raise ValueError('IMMUTABLE_CLAIMS_MISMATCH')
    return json.loads(path.read_text(encoding='utf-8')),sha


def claim_evidence_ids(claims):
    """Existing observation identities belonging to one extraction contract.

    Historical rows remain in SQLite. This set is a selection boundary, not
    an update, deletion, new identity scheme or latest-date overwrite.
    """
    active=set()
    for p in claims['projects']:
        eid='AU-'+digest([p.get('entity_namespace','project_registry_v1'),str(p['id'])])[:20]
        for o in p['observations']:active.add(digest([eid,o['source_sha256'],o]))
    for event in claims.get('events',[]):
        eid='AU-'+digest([event['project_namespace'],str(event['project_native_id'])])[:20]
        raw=dict(event,variable='commercial_event',domain=event.get('domain','Commercial'),value=None)
        active.add(digest([eid,event['source_sha256'],raw]))
    return active


def ingest_events(db, root, snapshots, cutoff, claims_data=None):
    """Typed disclosures in the existing observation store; numeric value NULL."""
    from .selection import date_end
    sources = {s['key']: s for s in snapshots}
    cache = {}
    events = (claims_data if claims_data is not None else json.loads((Path(root)/'data/claims.json').read_text(encoding='utf-8'))).get('events', [])
    for event in events:
        source = sources.get(event['source_key'])
        if not source:
            continue
        eid = 'AU-' + digest([event['project_namespace'], str(event['project_native_id'])])[:20]
        if not db.execute('SELECT 1 FROM entities WHERE entity_id=?', (eid,)).fetchone():
            issue(db, eid, source['sha256'], 'EVENT_PROJECT_NOT_REGISTERED', event['event_id'])
            continue
        reasons = []
        try:
            if date_end(event['effective_date']) > cutoff:
                continue
            validate_pages(root, source, event, snapshots, cache)
            if event.get('attribution') not in ('PROJECT', 'COMPANY') or not event.get('scope') or not event.get('event_id'):
                raise ValueError('INVALID_COMMERCIAL_EVENT_CONTRACT')
        except (ValueError, KeyError, IndexError, OSError, TypeError) as exc:
            reasons.append(str(exc) or type(exc).__name__)
        raw = dict(event, variable='commercial_event', domain=event.get('domain','Commercial'), value=None)
        obsid = digest([eid, source['sha256'], raw])
        db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (obsid, eid, 'commercial_event', None, None, 'DATED_COMMERCIAL_DISCLOSURE',
                    event['scope'], event['event_id'], None, event['effective_date'], source['sha256'],
                    event['locator'], 'AUTO_VALIDATED' if not reasons else 'REVIEW', canonical(reasons),
                    canonical(raw), 'commercial-event-v1'))
        for reason in reasons:
            issue(db, eid, source['sha256'], 'COMMERCIAL_EVENT_INVALID', canonical([event['event_id'], reason]))


def ingest_recognized(db, root, snapshots, cutoff, policy, acquired_through=None):
    """Automatic raw observations reuse the canonical table and shared checks.

    Resource-table observations retain a reported_ prefix until a compatible
    resource scope/effective date is established. Text disclosures have NULL
    numerical values and cannot accidentally satisfy an MCDA criterion.
    """
    from .selection import source_check, date_end
    from .store import filehash
    root=Path(root);sources={s['sha256']:s for s in snapshots};outcomes=[]
    for artifact in snapshots:
        if artifact['kind']!='document_extraction':continue
        try:
            if source_check(artifact,cutoff,root,acquired_through):raise ValueError('EXTRACTION_ARTIFACT_INVALID')
            data=json.loads((root/artifact['path']).read_text(encoding='utf-8'))
            source=sources.get(data['source_sha256'])
            if source_check(source,cutoff,root,acquired_through):raise ValueError('ORIGINAL_SOURCE_INVALID_OR_OUTSIDE_LOCK')
            if artifact['source_sha256']!=source['sha256'] or data['version'] not in policy.get('parser_versions',[policy['parser_version']]):
                raise ValueError('PARSER_OR_SOURCE_VERSION_MISMATCH')
            pages={p['physical_page']:p for p in data['pages']}
            for candidate in data['candidates']:
                from .pdf_extract import candidate_value_issues
                c=dict(candidate);reasons=list(c['issues'])+candidate_value_issues(c);pid=c.get('project_id')
                page=pages.get(c['physical_page'])
                if not page or re.sub(r'\s+',' ',c['raw_text']) not in re.sub(r'\s+',' ',page['text']):
                    reasons.append('PAGE_TEXT_BINDING_FAILED')
                if policy.get('validation_version') and page:
                    from .pdf_extract import narrative_context_issues
                    reasons.extend(narrative_context_issues(c,page,version=policy['validation_version']))
                if c['source_sha256']!=source['sha256']:reasons.append('SOURCE_BINDING_FAILED')
                if not pid or not db.execute("SELECT 1 FROM entities WHERE entity_id=? AND kind='PROJECT'",(pid,)).fetchone():
                    outcomes.append(dict(candidate_id=c['candidate_id'],source_key=source['key'],
                                         status='OBSERVATION_EXTRACTED_NOT_VALIDATED',issues=canonical(sorted(set(reasons+['PROJECT_NOT_REGISTERED'])))))
                    continue
                reported_date=source.get('publication_date') or data.get('publication_date')
                if not reported_date:
                    reasons.append('PUBLICATION_DATE_NOT_ESTABLISHED')
                date=reported_date or source['available_date']
                if date_end(date)>cutoff:continue
                values={};component_basis={};component_metadata={}
                if c['kind']=='RESOURCE_TABLE_TOTAL':
                    for variable,value in c['values'].items():
                        original=dict(variable=variable,value=value,unit=c['units'][variable],basis=c['basis'],
                                      scope=c['scope'],locator='physical page '+str(c['physical_page']),
                                      statement_id=c['candidate_id'],category=c.get('category'))
                        reasons.extend(normalize(original))
                        values['reported_resource_'+variable]=(value,c['units'][variable])
                elif c['kind']=='TECHNICAL_TABLE_CELL':
                    values['reported_technical_'+c['quantity']]=(c['value'],c['unit'])
                elif c['kind']=='LEACH_TABLE_ROW':
                    for element,value in c['values'].items():
                        if not isinstance(value,(int,float)) or not 0<=value<=100:
                            reasons.append('PERCENT_OUT_OF_RANGE')
                        variable='reported_technical_extraction_'+element.lower()+'_pct'
                        values[variable]=(value,'%');component_basis[variable]=element
                else:
                    values['reported_'+c['domain'].lower()+'_disclosure']=(None,None)
                    if c['domain']=='Technical':
                        for i,number in enumerate(c.get('numbers',[])):
                            if number.get('quantity_role') and isinstance(number['value'],(int,float)) and 0<=number['value']<=100:
                                variable='reported_technical_'+number['quantity_role'].lower()+'_'+str(i)+'_pct'
                                values[variable]=(number['value'],'%')
                                if number.get('basis'):component_basis[variable]=number['basis']
                                if number.get('statistic'):component_metadata[variable]={k:number.get(k) for k in ('statistic','evidence_nature','quantity_role')}

                for i,ratio in enumerate(c.get('reported_ratios',[])):
                    values['reported_technical_'+ratio['quantity']+'_'+str(i)]=(ratio['value'],ratio['unit'])
                for extra in c.get('extra_values',[]):
                    if extra['unit']!='ppm':continue
                    domain='Technical' if extra['label'] in ('U','Th') else 'Strategic'
                    variable='reported_'+domain.lower()+'_'+extra['label'].lower()+'_ppm'
                    values[variable]=(extra['value'],'ppm');component_basis[variable]=extra['label']
                c.update(effective_date=date,date_role='DISCLOSURE_DATE_NOT_RESOURCE_EFFECTIVE_DATE',
                         source_key=source['key'],source_sha256=source['sha256'],
                         pdf_page=c['physical_page'] if source['kind']=='pdf' else None,
                         locator='physical page '+str(c['physical_page'])+'; row/paragraph '+str(c['row_index'])+('; table '+str(c['table_index'])+'; column '+str(c['column_index']) if c['kind']=='TECHNICAL_TABLE_CELL' else ''),
                         extraction_artifact_sha256=artifact['sha256'],statement_id=c['candidate_id'],
                         domain=c['domain'],role='AUTOMATIC_RAW_OBSERVATION_NOT_CRITERION_APPROVAL')
                if policy.get('validation_version'):c['validation_version']=policy['validation_version']
                status='REVIEW' if reasons else 'AUTO_VALIDATED'
                for variable,(value,unit) in values.items():
                    raw=dict(c,variable=variable,value=value,unit=unit,**component_metadata.get(variable,{}))
                    if variable in component_basis:
                        raw['source_total_basis']=raw.get('basis');raw['basis']=component_basis[variable]
                    if variable.startswith('reported_strategic_'):raw['domain']='Strategic'
                    elif variable.startswith('reported_technical_'):raw['domain']='Technical'
                    obsid=digest([pid,source['sha256'],raw])
                    db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                               (obsid,pid,variable,value,unit,raw.get('basis'),c['scope'],c['candidate_id'],
                                c.get('category'),date,source['sha256'],c['locator'],status,
                                canonical(sorted(set(reasons))),canonical(raw),data['version']))
                outcomes.append(dict(candidate_id=c['candidate_id'],source_key=source['key'],project_id=pid,
                                     status=status,observations=len(values),issues=canonical(sorted(set(reasons)))))
        except (ValueError,KeyError,TypeError,OSError) as exc:
            issue(db,None,artifact['sha256'],'DOCUMENT_EXTRACTION_INVALID',str(exc))
            outcomes.append(dict(source_key=artifact['key'],status='EXTRACTION_FAILED',issues=str(exc)))
    return outcomes


def document_report(root, snapshots, outcomes, out, shared_comparability=False):
    """Measured acquisition/extraction inventory; never count tables as Projects."""
    from .analysis import write_csv
    from collections import Counter
    root=Path(root);out=Path(out);documents=[];candidates=[];process=[]
    for artifact in snapshots:
        if artifact['kind']!='document_extraction':continue
        data=json.loads((root/artifact['path']).read_text(encoding='utf-8'))
        documents.append(dict(source_key=data['source_key'],source_sha256=data['source_sha256'],
                              extraction_sha256=artifact['sha256'],parser_version=data['version'],
                              publication_date=data.get('publication_date'),labels=canonical(data['labels']),
                              pages=len(data['pages']),relevant_pages=sum(p['relevant'] for p in data['pages']),
                              unreadable_pages=sum(p['status']=='UNREADABLE' for p in data['pages']),
                              tables=len(data['tables']),candidates=len(data['candidates']),
                              source_url=data['source_url']))
        for c in data['candidates']:
            candidates.append(dict(candidate_id=c['candidate_id'],source_key=data['source_key'],
                                   source_sha256=data['source_sha256'],project_id=c.get('project_id'),
                                   domain=c['domain'],kind=c['kind'],physical_page=c['physical_page'],
                                   scope=c['scope'],issues=canonical(c['issues']),raw_text=c['raw_text']))
            if c['kind']=='LEACH_TABLE_ROW':
                process.append({k:c.get(k) for k in ('candidate_id','project_id','source_sha256','physical_page','scope','sample_id','sample_interval','statistic','endpoint','feed','scale','basis','reagent','temperature_c','residence_hours','acid_concentration','pressure')})
    write_csv(out/'document_inventory.csv',documents,
              ['source_key','source_sha256','extraction_sha256','parser_version','publication_date','labels','pages','relevant_pages','unreadable_pages','tables','candidates','source_url'])
    write_csv(out/'document_candidates.csv',candidates,
              ['candidate_id','source_key','source_sha256','project_id','domain','kind','physical_page','scope','issues','raw_text'])
    # "Latest related report" is a discovery aid, not a scope replacement.
    related=[]
    for project in sorted({c['project_id'] for c in candidates if c['project_id']}):
        relevant={c['source_sha256'] for c in candidates if c['project_id']==project}
        for label in sorted({v for d in documents if d['source_sha256'] in relevant for v in json.loads(d['labels'])}):
            family=[d for d in documents if d['source_sha256'] in relevant and label in json.loads(d['labels'])]
            dated=[d for d in family if d['publication_date']]
            latest=max((d['publication_date'] for d in dated),default=None)
            for d in family:
                related.append(dict(project_id=project,document_type_mention=label,source_sha256=d['source_sha256'],
                                    publication_date=d['publication_date'],latest_related_disclosure=d['publication_date']==latest if latest else None,
                                    replaces_source_sha256=None,replacement_status='NOT_ESTABLISHED_DIFFERENT_SCOPE_OR_DATE_NOT_SUFFICIENT'))
    write_csv(out/'document_versions.csv',related,
              ['project_id','document_type_mention','source_sha256','publication_date','latest_related_disclosure','replaces_source_sha256','replacement_status'])
    write_csv(out/'document_process_variables.csv',process,
              ['candidate_id','project_id','source_sha256','physical_page','scope','sample_id','sample_interval','statistic','endpoint','feed','scale','basis','reagent','temperature_c','residence_hours','acid_concentration','pressure'])
    groups={}
    dimensions=('statistic','endpoint','feed','scale','basis','reagent','temperature_c','residence_hours','acid_concentration','pressure')
    for row in process:
        if row['project_id']:groups.setdefault(canonical([row[k] for k in dimensions]),[]).append(row)
    if not shared_comparability:write_csv(out/'document_recovery_groups.csv',
              [dict(comparison_contract=key,projects=len({r['project_id'] for r in group}),test_rows=len(group),
                    status='CONDITIONS_INCOMPLETE_NO_COMMON_SCORE' if any(r[k] is None for r in group for k in ('acid_concentration','pressure')) else 'SINGLE_PROJECT_NO_RANK',
                    source_shas=canonical(sorted({r['source_sha256'] for r in group}))) for key,group in sorted(groups.items())],
              ['comparison_contract','projects','test_rows','status','source_shas'])
    counts=Counter(c['status'] for c in outcomes)
    report=dict(documents=len(documents),pages=sum(d['pages'] for d in documents),
                relevant_pages=sum(d['relevant_pages'] for d in documents),tables=sum(d['tables'] for d in documents),
                candidates=len(candidates),candidate_statuses=dict(counts),
                validated_observations=sum(c.get('observations',0) for c in outcomes if c['status']=='AUTO_VALIDATED'),
                limitations=['RAW_VALIDATION_IS_NOT_FORMAL_CRITERION_APPROVAL','NO_CORPUS_WIDE_RECALL_CLAIM'])
    (out/'document_pipeline_summary.json').write_text(canonical(report)+'\n',encoding='utf-8')
    return report

def ingest_sources(db, root, snapshots, commodity_version="minedex-commodity-v2", candidate_version=None):
    for s in snapshots:
        db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?)',
                   (s['sha256'], s['key'], s['url'], s.get('publication_date'),
                    s['acquired_at'], s['path'], s['kind'], canonical(s)))
        if s['kind']=='minedex_resource_batch':
            from .official import ingest_minedex_resources
            try:ingest_minedex_resources(db,root,s,commodity_version)
            except Exception as exc:issue(db,None,s['sha256'],'MINEDEX_RESOURCE_INGEST_FAILED',str(exc))
            continue
        if s.get('national_government'):
            from .national import ingest_government
            try:ingest_government(db,root,s,candidate_version)
            except Exception as exc:issue(db,None,s['sha256'],'GOVERNMENT_SOURCE_INGEST_FAILED',str(exc))
            continue
        if s['kind']=='legacy_screen_index':
            ingest_screen_index(db,root,s)
            continue
        if s['kind'] == 'historical_e1_candidates':
            ingest_legacy_e1(db,root,s)
            continue
        if s['kind'] == 'official_project_catalogue_transcription':
            ingest_prospectus(db,root,s)
            continue
        if s['kind'] == 'official_table_transcription':
            ingest_official_table(db,root,s)
            continue
        if s['kind'] == 'xlsx_census':
            ingest_workbook(db,root,s)
            continue
        if s['kind'] != 'arcgis_census':
            continue
        raw = json.loads((Path(root) / s['path']).read_text(encoding='utf-8'))
        for feature in raw['features']:
            a = feature['attributes']
            if s.get('commodity_pattern') and not re.search(s['commodity_pattern'],str(a.get(s['commodity_field'],'')),re.I):
                continue
            native = a.get(s['id_field'])
            if native is None:
                issue(db, None, s['sha256'], 'MISSING_NATIVE_ID', canonical(a))
                continue
            eid = entity(db, s['namespace'], native, s['entity_kind'])
            lon, lat = a.get('longitude'), a.get('latitude')
            if lon is None or lat is None:
                g = feature.get('geometry') or {}
                lon, lat = g.get('x'), g.get('y')
            if lon is not None and lat is not None and not (110 <= lon <= 155 and -45 <= lat <= -9):
                issue(db, eid, s['sha256'], 'COORDINATE_RANGE', canonical([lon, lat]))
                lon = lat = None
            db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                       (eid, s['sha256'], a[s['name_field']], a.get('state'), lon, lat,
                        a.get('mineraldeposittype'), a.get(s.get('activity_field','currentstatus')), canonical(a)))

def normalize(observation):
    """Mt × % -> kt = Mt × percent × 10; Mt × ppm -> kt = Mt × ppm / 1000."""
    o = observation
    reasons = []
    value = o.get('value')
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    textual=o.get('kind')=='SOURCE_BOUND_SCIENTIFIC_CLAIM'
    if textual and (value is not None or not o.get('raw_text') or not o.get('reviewed_interpretations')):reasons.append('INVALID_TEXTUAL_SCIENTIFIC_CLAIM')
    if not numeric and not textual:
        reasons.append('MISSING_OR_NONFINITE')
    elif numeric and value < 0:
        reasons.append('NEGATIVE_VALUE')
    if numeric and o.get('unit')=='%' and value>100:reasons.append('PERCENT_OUT_OF_RANGE')
    if numeric and o['variable'] in ('ore_mt','grade','contained_treo_kt') and value<=0:reasons.append('NONPOSITIVE_RESOURCE_VALUE')
    if o['variable'].startswith('reported_') and o['variable'].endswith('_ppm') and (o.get('unit')!='ppm' or (numeric and value>1000000)):
        reasons.append('INVALID_OXIDE_PPM_COMPONENT')
    if o.get('basis') != 'TREO' and o['variable'] in ('ore_mt', 'grade', 'contained_treo_kt'):
        reasons.append('NONCOMPARABLE_BASIS')
    if o['variable'] == 'grade':
        if o.get('unit') not in ('%', 'ppm'):
            reasons.append('UNSUPPORTED_GRADE_UNIT')
        elif numeric and value > (100 if o['unit'] == '%' else 1_000_000):
            reasons.append('GRADE_OUT_OF_RANGE')
    if not o.get('locator') or not o.get('scope') or not o.get('statement_id'):
        reasons.append('MISSING_SCOPE_OR_LOCATOR')
    if o.get('category') in ('EXPLORATION_TARGET', 'RESERVE') and o['variable'] in ('ore_mt', 'grade'):
        reasons.append('NOT_MINERAL_RESOURCE')
    if o['variable'] in ('ore_mt', 'grade','contained_treo_kt') and o.get('category') not in (
        'MEASURED','INDICATED','INFERRED','MEASURED_INDICATED_INFERRED_TOTAL','MEASURED_INDICATED_TOTAL','INDICATED_INFERRED_TOTAL','MEASURED_INFERRED_TOTAL'):
        reasons.append('UNSUPPORTED_RESOURCE_CATEGORY')
    if o.get('review_required'):
        reasons.append('SCIENTIFIC_REVIEW_REQUIRED')
    return sorted(set(reasons))

def transformation_issues(o, siblings, depth=0):
    """Explicit oxide-basis reconciliation; same statement, scope, date and source only."""
    t=o.get('transform')
    if not t:return []
    if depth>3:return ['TRANSFORMATION_CYCLE_OR_DEPTH']
    try:
        if t['rule']=='BT_TO_MT':
            assert t['original_unit']=='Bt' and o['unit']=='Mt' and math.isclose(o['value'],t['original_value']*1000)
        elif t['rule']=='OXIDE_DISTRIBUTION_PERCENT_TO_PPM':
            assert t['original_unit']=='% of TREO' and o['unit']=='ppm'
            assert o['basis'] in {'Pr6O11','Nd2O3','Tb4O7','Dy2O3','TREO'}
            assert o.get('material_basis')=='OXIDE_DISTRIBUTION_NOT_ORE_GRADE'
            assert 0<=t['original_value']<=100 and math.isclose(o['value'],t['original_value']*10000)
        elif t['rule']=='REO_DISTRIBUTION_DENOMINATOR':
            assert o['basis']=='TREO' and o['unit']=='ppm' and o['value']==1000000
            assert o.get('material_basis')=='OXIDE_DISTRIBUTION_NOT_ORE_GRADE'
            assert o.get('derivation_status')=='DEFINITION_IDENTITY_NOT_REPORTED_MEASUREMENT'
        else:
            inputs=[]
            for var in t['inputs']:
                matches=[x for x in siblings if x['variable']==var and all(x.get(k)==o.get(k) for k in ('scope','statement_id','effective_date','source_key','source_sha256'))]
                assert len(matches)==1
                x=matches[0]
                assert not normalize(x) and not transformation_issues(x,siblings,depth+1) and x['unit']=='ppm'
                inputs.append(x)
            if t['rule']=='SUM_OXIDE_PPM':
                assert len(inputs)==2 and {x['basis'] for x in inputs}=={'LANTHANIDE_OXIDES','Y2O3'} and o['basis']=='TREO' and o['unit']=='ppm'
                expected=sum(x['value'] for x in inputs)
            elif t['rule']=='SUM_MAGNET_OXIDE_PPM':
                assert len(inputs)==4 and {x['basis'] for x in inputs}=={'Pr6O11','Nd2O3','Tb4O7','Dy2O3'} and o['basis']=='PrNdDyTb_OXIDES' and o['unit']=='ppm'
                expected=sum(x['value'] for x in inputs)
            elif t['rule']=='RATIO_PPM_PERCENT':
                assert len(inputs)==2 and inputs[0]['basis']=='PrNdDyTb_OXIDES' and inputs[1]['basis']=='TREO' and inputs[1]['value']>0 and o['unit']=='%'
                expected=100*inputs[0]['value']/inputs[1]['value']
            else:return ['UNSUPPORTED_TRANSFORMATION']
            assert math.isclose(o['value'],expected,rel_tol=1e-10)
    except (AssertionError,KeyError,TypeError,ValueError,ZeroDivisionError):return ['TRANSFORMATION_CONTRACT_FAILED']
    return []

def ingest_claims(db, root, snapshots, cutoff, project=None, conflict_selection=False, claims_data=None):
    by_key = {s['key']: s for s in snapshots}
    readers={};page_text={}
    claims = claims_data if claims_data is not None else json.loads((Path(root) / 'data/claims.json').read_text(encoding='utf-8'))
    for p in claims['projects']:
        if project and p['id'] != project:
            continue
        if any(key not in by_key for key in p.get('required_source_keys',[])):continue
        source = by_key.get(p['identity_source'])
        if not source:
            continue
        eid = entity(db, p.get('entity_namespace','project_registry_v1'), p['id'], p.get('entity_kind','PROJECT'))
        db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                   (eid, source['sha256'], p['name'], p['state'], p.get('longitude'), p.get('latitude'),
                    p.get('deposit_type'), None, canonical(p)))
        coordinate_source = by_key.get(p.get('coordinate_source'))
        if coordinate_source:
            dep = db.execute('''SELECT r.* FROM records r JOIN entities e USING(entity_id)
                WHERE e.native_namespace=? AND e.native_id=? AND r.source_sha=?''',
                (coordinate_source['namespace'], str(p['coordinate_native_id']), coordinate_source['sha256'])).fetchone()
            if dep:
                db.execute('INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?,?,?)',
                    (eid, coordinate_source['sha256'], p['name'], p['state'],dep['longitude'],dep['latitude'],
                     p.get('deposit_type'), None, canonical(p)))
                # The legacy key omitted the source revision. Keep old rows,
                # but allow an unchanged native point in a new source snapshot.
                # Do not duplicate a relation already stored under a legacy key.
                db.execute('''INSERT OR IGNORE INTO relations SELECT ?,?,?,?,?,?,?
                    WHERE NOT EXISTS (SELECT 1 FROM relations
                        WHERE parent_id=? AND child_id=? AND relation=? AND source_sha=?)''',
                    (digest([eid,dep['entity_id'],'REPRESENTATIVE_POINT',coordinate_source['sha256']]),eid,dep['entity_id'],
                     'REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE',coordinate_source['available_date'],
                     coordinate_source['sha256'],p['coordinate_role'],eid,dep['entity_id'],
                     'REPRESENTATIVE_POINT_NOT_ENTITY_EQUIVALENCE',coordinate_source['sha256']))
        for o in p['observations']:
            s = by_key.get(o['source_key'])
            if not s or o['effective_date'] > cutoff:
                continue
            reasons = normalize(o)+transformation_issues(o,p['observations'])
            # Claim binding prevents silently applying old extraction to a changed PDF.
            if o['source_sha256'] != s['sha256']:
                reasons.append('EXTRACTION_VERSION_MISMATCH')
            if s['kind']=='html':
                try:
                    text=html_text(root,s)
                    if not o.get('source_markers') or not all(marker in text for marker in o['source_markers']):
                        reasons.append('EXTRACTION_HTML_MARKER_CHECK_FAILED')
                except (ValueError,OSError):
                    reasons.append('EXTRACTION_HTML_READ_FAILED')
            if s['kind']=='pdf' and o.get('pdf_page'):
                try:
                    validate_pages(root,s,o,snapshots,page_text)
                except Exception:
                    reasons.append('EXTRACTION_READ_FAILED')
            obsid = digest([eid, s['sha256'], o])
            db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (obsid, eid, o['variable'], o.get('value'), o.get('unit'), o.get('basis'),
                        o['scope'], o['statement_id'], o.get('category'), o['effective_date'],
                        s['sha256'], o['locator'], 'AUTO_VALIDATED' if not reasons else 'REVIEW',
                        canonical(reasons), canonical(o), 'normalization-v1'))
            for reason in reasons:
                issue(db, eid, s['sha256'], reason, obsid)
    # Conflicting same-date, same-scope values are never resolved by insertion order.
    if conflict_selection:
        return  # Current selection records conflicts without mutating originals.
    groups = db.execute('''SELECT entity_id,variable,scope,effective_date,COUNT(DISTINCT value) n
        FROM observations WHERE status='AUTO_VALIDATED' GROUP BY entity_id,variable,scope,effective_date HAVING n>1''').fetchall()
    for g in groups:
        params = tuple(g[k] for k in ('entity_id', 'variable', 'scope', 'effective_date'))
        db.execute('''UPDATE observations SET status='REVIEW' WHERE entity_id=? AND variable=?
                      AND scope=? AND effective_date=? AND status='AUTO_VALIDATED' ''', params)
        issue(db, g['entity_id'], None, 'SOURCE_CONFLICT', canonical(dict(g)))

def resource_values(db, cutoff, snapshot_shas, strict=False, active_claim_ids=None):
    """Pick latest complete statement per scope; competing scopes require review."""
    result = {}
    projects = [r[0] for r in db.execute("SELECT entity_id FROM entities WHERE kind='PROJECT'")]
    for eid in projects:
        rows = [dict(r) for r in db.execute('''SELECT * FROM observations
            WHERE entity_id=? AND effective_date<=? AND status='AUTO_VALIDATED'
            ORDER BY effective_date,obs_id''', (eid, cutoff)) if r['source_sha'] in snapshot_shas and
                (active_claim_ids is None or r['transform_version']!='normalization-v1' or r['obs_id'] in active_claim_ids)]
        statements = {}
        for r in rows:
            key=(r['statement_id'], r['scope'], r['effective_date'])
            if strict:key=(*key,r['source_sha'])
            statements.setdefault(key, {})[r['variable']] = r
        valid = []
        for key, values in statements.items():
            sid, scope, date=key[:3]
            if not {'ore_mt', 'grade'} <= values.keys():
                continue
            ore, grade = values['ore_mt'], values['grade']
            if ore['unit'] != 'Mt' or ore['basis'] != grade['basis'] or ore['source_sha'] != grade['source_sha']:
                continue
            contained = ore['value'] * grade['value'] * (10 if grade['unit'] == '%' else .001)
            ore_raw, grade_raw = json.loads(ore['raw']), json.loads(grade['raw'])
            ore_half = ore_raw.get('rounding_half_width') or 0
            grade_half = grade_raw.get('rounding_half_width') or 0
            factor = 10 if grade['unit']=='%' else .001
            bounds = [(ore['value']-ore_half)*(grade['value']-grade_half)*factor,
                      (ore['value']+ore_half)*(grade['value']+grade_half)*factor]
            reported = values.get('contained_treo_kt')
            if reported and not bounds[0] <= reported['value'] <= bounds[1]:
                issue(db,eid,reported['source_sha'],'REPORTED_CONTAINED_CONFLICT',canonical([reported['value'],bounds]))
                continue
            valid.append({'entity_id': eid, 'statement_id': sid, 'scope': scope, 'date': date,
                          'ore_mt': ore['value'], 'grade_pct': grade['value'] if grade['unit']=='%' else grade['value']/10000,
                          'contained_treo_kt': reported['value'] if reported else contained,
                          'calculated_from_rounded_inputs_kt':contained,'rounding_bounds_kt':bounds,
                          'obs_ids': [ore['obs_id'], grade['obs_id']] + ([reported['obs_id']] if reported else []),
                          'source_sha': ore['source_sha'], 'basis': 'TREO',
                          'interpretation': 'IN_SITU_RESOURCE_NOT_RECOVERABLE_PRODUCT'})
        if not valid:
            continue
        if strict:
            from .selection import choose
            candidates=[dict(v,evidence_id=digest(v),source_sha256=v['source_sha'],effective_date=v['date'],
                             value={k:v[k] for k in ('ore_mt','grade_pct','contained_treo_kt')}) for v in valid]
            chosen,reason=choose(candidates,('scope','basis'))
            if chosen is None:
                issue(db,eid,None,'RESOURCE_SCOPE_AMBIGUITY',reason)
                continue
            selected=next(v for v in valid if digest(v)==chosen['evidence_id'])
            result[eid]=selected
            continue
        latest = max(v['date'] for v in valid)
        active = [v for v in valid if v['date'] == latest]
        if len(active) != 1:
            issue(db, eid, None, 'RESOURCE_SCOPE_AMBIGUITY', canonical(active))
            continue
        result[eid] = active[0]
    return result
