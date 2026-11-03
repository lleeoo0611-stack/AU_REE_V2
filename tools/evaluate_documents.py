"""A bounded, rendered-page benchmark; never an input to evidence ingestion."""
import json
import sys
from pathlib import Path
from collections import Counter


def evaluate(root, legacy=False):
    root=Path(root)
    # Historical benchmarks describe the extraction artifacts actually evaluated,
    # never whichever parser derivatives happen to be newest in the manifest.
    phase=9 if legacy else 10
    snapshots=json.loads((root/f'results/phase{phase}-2026-11-03/snapshot_lock.json').read_text())
    artifacts={s['source_sha256']:json.loads((root/s['path']).read_text(encoding='utf-8'))
               for s in snapshots if s['kind']=='document_extraction'}
    by_key={s['key']:s for s in snapshots}
    # Ground truth is used exclusively for evaluation. These selected cells were
    # checked against rendered originals; there is no corpus-wide recall claim.
    gold=[('mt_weld_2024',2,'Total',{'ore_mt':106.6,'grade':4.1,'contained_treo_kt':4389.}),
          ('yttria_maiden2024',2,'Total',{'ore_mt':15.,'grade':490.,'MREO':110.,'LREO':220.,'HREO':270.,
                                      'Pr6O11':15.,'Nd2O3':64.,'Dy2O3':24.,'Tb4O7':3.7,'Sc2O3':68.,'U':.6,'Th':1.}),
          ('discovery_asra_primary_met_alternative_530e7a5f3d94',2,'Avg:HCl',
           {'TREO':66.,'MREO':78.,'Pr6O11':85.,'Nd2O3':85.,'Tb4O7':69.,'Dy2O3':62.,'Sc2O3':23.}),
          ('discovery_asra_primary_met_alternative_530e7a5f3d94',2,'Avg:Sulfuric and Magnesium Chloride',
           {'TREO':49.,'MREO':61.,'Pr6O11':67.,'Nd2O3':67.,'Tb4O7':52.,'Dy2O3':46.,'Sc2O3':29.}),
          # Difficult layouts remain held out; misses must remain in the metric.
          ('koppamurra_pfs2026',8,'Total',{'ore_mt':243.,'grade':751.}),
          ('browns_range_2025',54,'Total',{'ore_mt':7.3,'grade':.96})]
    tp=fp=fn=located=unit_correct=0;cells=[]
    for key,page,row_label,expected in gold:
        data=artifacts[by_key[key]['sha256']]
        rows=[c for c in data['candidates'] if c['physical_page']==page and c['kind'] in ('RESOURCE_TABLE_TOTAL','LEACH_TABLE_ROW') and not c['issues']]
        if row_label.startswith('Avg:'):
            reagent=row_label.split(':',1)[1]
            rows=[c for c in rows if c.get('sample_id')=='Avg' and c.get('reagent')==reagent]
        found={}
        if len(rows)==1:
            found={**rows[0]['values'],**{e['label']:e['value'] for e in rows[0].get('extra_values',[])}}
        for variable,value in expected.items():
            actual=found.get(variable)
            expected_unit='%' if row_label.startswith('Avg:') else ('Mt' if variable=='ore_mt' else 'kt TREO' if variable=='contained_treo_kt' else '%' if key=='mt_weld_2024' else 'ppm')
            if not legacy and key=='browns_range_2025' and variable=='grade':expected_unit='%'
            actual_unit=(rows[0].get('unit') or rows[0].get('units',{}).get(variable) or next((e['unit'] for e in rows[0].get('extra_values',[]) if e['label']==variable),None)) if len(rows)==1 else None
            if actual==value and actual_unit==expected_unit:
                tp+=1;unit_correct+=1;located+=bool(rows[0]['physical_page'] and rows[0]['source_sha256']);status='EXACT'
            elif actual is None:fn+=1;status='NOT_VALIDATED_LAYOUT_OR_SCOPE'
            else:fp+=1;fn+=1;status='VALUE_OR_COLUMN_ERROR'
            cells.append(dict(source_key=key,physical_page=page,row_label=row_label,variable=variable,expected=value,actual=actual,expected_unit=expected_unit,actual_unit=actual_unit,status=status))
    return dict(version='rendered-cell-benchmark-v1' if legacy else 'rendered-cell-benchmark-v2-corrected-wolverine-unit',scope='SELECTED_CELLS_SIX_TABLE_SCOPES_FIVE_DOCUMENTS_NOT_CORPUS_WIDE',
                cells=len(cells),true_positive=tp,false_positive=fp,false_negative=fn,
                precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None,
                unit_contract='Mt_or_percent_or_ppm_as_printed; element columns kept separate',
                source_locator_completeness_of_validated=located/tp if tp else None,
                unit_accuracy_of_validated=unit_correct/tp if tp else None,results=cells)


def evaluate_phase12(root, validation_version='scientific-context-v4-column-binding', parser_version='document-recognition-v2-mineralogy', numeric_cases=None, decision_cases=None):
    """Selected original-page evaluation, separate from production ingestion.

    The labels below were checked on rendered originals. They are evaluation
    labels only and never used to create database observations. Positive cells
    and acceptance/rejection decisions have separate denominators. This is a
    deliberately difficult, purposive sample, not a blind or national estimate.
    """
    import re
    import pymupdf
    from au_ree_v2.pdf_extract import (project_registry, resource_rows,
        positioned_resource_columns, leach_tables, narrative_candidates,
        candidate_value_issues, narrative_context_issues, DOCUMENT_VERSION)
    from au_ree_v2.store import filehash
    root=Path(root)
    manifest=json.loads((root/'data/manifest.json').read_text(encoding='utf-8'))
    sources={s['key']:s for s in manifest['snapshots'] if s['kind']=='pdf'}
    registry=project_registry(root)
    projects={r['native_id']:r['entity_id'] for r in registry}
    # Units are as printed except contained tonnes -> kt, an explicit /1000
    # conversion already defined by the production resource parser.
    numeric=[
        dict(key='mt_weld_2024',page=2,row=r'^Total\s+106\.6\b',project='mt-weld',scope=r'Mt Weld.*Mineral Resource',
             values={'ore_mt':106.6,'grade':4.1,'contained_treo_kt':4389.},units={'ore_mt':'Mt','grade':'%','contained_treo_kt':'kt TREO'}),
        dict(key='koppamurra_pfs2026',page=8,row=r'^Total\s+243\b',project='2298466',scope=r'Global Mineral Resource.*Koppamurra',
             values={'ore_mt':243.,'grade':751.,'Pr6O11':35.,'Nd2O3':132.},units={'ore_mt':'Mt','grade':'ppm','Pr6O11':'ppm','Nd2O3':'ppm'}),
        dict(key='koppamurra_pfs2026',page=8,row=r'^Total\s+4\s+19\b',project='2298466',scope=r'Global Mineral Resource',
             values={'Tb4O7':4.,'Dy2O3':19.},units={'Tb4O7':'ppm','Dy2O3':'ppm'}),
        dict(key='browns_range_2025',page=54,row=r'^Total\s+7\.3\b',project='browns-range',scope=r'Wolverine Mineral Resource',
             values={'ore_mt':7.3,'grade':.96},units={'ore_mt':'Mt','grade':'%'}),
        dict(key='browns_range_2025',page=55,row=r'^Total\s+7\.5\b',project='browns-range',scope=r'DFS component.*Mineral Resource',
             values={'ore_mt':7.5,'grade':.96},units={'ore_mt':'Mt','grade':'%'}),
        dict(key='yangibana_ar2026',page=14,row=r'^TOTAL\s+29\.93\b',project='yangibana',scope=r'Yangibana.*Mineral Resource',
             values={'ore_mt':29.93,'grade':.93,'contained_treo_kt':276.955},units={'ore_mt':'Mt','grade':'%','contained_treo_kt':'kt TREO'}),
        dict(key='cummins_mre2023',page=2,row=r'^Total\s+414\.8\b',project='cummins-range',scope=r'Cummins Range Mineral Resource',
             values={'ore_mt':414.8,'grade':3320.},units={'ore_mt':'Mt','grade':'ppm'}),
        dict(key='cummins_mre2023',page=2,row=r'^Total\s+104\.6\b',project='cummins-range',scope=r'Cummins Range Mineral Resource',
             values={'ore_mt':104.6,'grade':2590.},units={'ore_mt':'Mt','grade':'ppm'}),
        dict(key='cummins_mre2023',page=2,row=r'^Total\s+519\.3\b',project='cummins-range',scope=r'Cummins Range Mineral Resource',
             values={'ore_mt':519.3,'grade':3170.},units={'ore_mt':'Mt','grade':'ppm'}),
    ]
    decisions=[
        dict(label='resource_total',key='mt_weld_2024',page=2,pattern=r'^Total\s+106\.6\b',kind='RESOURCE_TABLE_TOTAL',project='mt-weld',accept=True),
        dict(label='cross_page_same_headers_reserve_not_resource',key='mt_weld_2024',page=3,pattern=r'^Total\s+32\.0\b',kind='RESOURCE_TABLE_TOTAL',project='mt-weld',accept=False),
        dict(label='resource_not_density_or_TREO_minus_Ce',key='koppamurra_pfs2026',page=8,pattern=r'^Total\s+243\b',kind='RESOURCE_TABLE_TOTAL',project='2298466',accept=True),
        dict(label='reserve_subset_not_added_to_resource',key='koppamurra_pfs2026',page=8,pattern=r'^Probable\s+26\b',kind='RESOURCE_TABLE_TOTAL',project='2298466',accept=False),
        dict(label='Wolverine_scope',key='browns_range_2025',page=54,pattern=r'^Total\s+7\.3\b',kind='RESOURCE_TABLE_TOTAL',project='browns-range',accept=True),
        dict(label='DFS_Wolverine_plus_stockpile_distinct_scope',key='browns_range_2025',page=55,pattern=r'^Total\s+7\.5\b',kind='RESOURCE_TABLE_TOTAL',project='browns-range',accept=True),
        dict(label='Yangibana_MRE_100pct_project_basis',key='yangibana_ar2026',page=14,pattern=r'^TOTAL\s+29\.93\b',kind='RESOURCE_TABLE_TOTAL',project='yangibana',accept=True),
        dict(label='Yangibana_reserve_not_MRE',key='yangibana_ar2026',page=14,pattern=r'^TOTAL\s+20\.92\b',kind='RESOURCE_TABLE_TOTAL',project='yangibana',accept=False),
        dict(label='Nb2O5_not_TREO',key='yangibana_ar2026',page=14,pattern=r'^TOTAL\s+6\.74\b',kind='RESOURCE_TABLE_TOTAL',project='yangibana',accept=False),
        dict(label='Brockman_not_Yangibana',key='yangibana_ar2026',page=14,pattern=r'^TOTAL\s+41\.6\b',kind='RESOURCE_TABLE_TOTAL',project='yangibana',accept=False),
        dict(label='THM_reserve_not_TREO_resource',key='donald_ar2024',page=32,pattern=r'^Total\s+825\b',kind='RESOURCE_TABLE_TOTAL',project='donald-rare-earth-mineral-sands-project',accept=False),
        dict(label='THM_resource_not_TREO',key='donald_ar2024',page=33,pattern=r'^Total\s+5,783\b',kind='RESOURCE_TABLE_TOTAL',project='donald-rare-earth-mineral-sands-project',accept=False),
        dict(label='glossary_not_completed_DFS',key='donald_ar2024',page=114,pattern=r'GLOSSARY OF ABBREVIATIONS',kind='SCOPED_TEXT_DISCLOSURE',project='donald-rare-earth-mineral-sands-project',accept=False),
        dict(label='project_activity_disclosure_not_FID_completion',key='nolans_ar2025',page=18,pattern=r'principal continuing activities.*advancing the Nolans Project',kind='SCOPED_TEXT_DISCLOSURE',project='nolans-rare-earths-project',accept=True),
        dict(label='company_cash_not_project_funds',key='nolans_ar2025',page=8,pattern=r'Based on our cash position',kind='SCOPED_TEXT_DISCLOSURE',project='nolans-rare-earths-project',accept=False),
        dict(label='future_funding_terms_not_completed_event',key='jupiter_scoping2026',page=50,pattern=r'The terms of any future funding',kind='SCOPED_TEXT_DISCLOSURE',project='jupiter',accept=False),
        dict(label='forward_looking_definition_not_technical_result',key='jupiter_scoping2026',page=50,pattern=r'Forward-looking statements include',kind='SCOPED_TEXT_DISCLOSURE',project='jupiter',accept=False),
    ]
    for label,ore,treo,phosphate in (('Rare_Dyke',414.8,3320.,4.2),('Phos_Dyke',104.6,2590.,5.9),('Combined',519.3,3170.,4.6)):
        row=r'^Total\s+'+re.escape(str(ore))+r'\b'
        common=dict(key='cummins_mre2023',page=2,pattern=row,kind='RESOURCE_TABLE_TOTAL',project='cummins-range')
        decisions.append(dict(common,label='Cummins_'+label+'_correct_TREO_column',accept=True,required_values={'ore_mt':ore,'grade':treo}))
        decisions.append(dict(common,label='Cummins_'+label+'_P2O5_not_TREO',accept=False,forbidden_grade=phosphate))
    if numeric_cases is not None:numeric=numeric_cases
    if decision_cases is not None:decisions=decision_cases
    requested={(c['key'],c['page']) for c in numeric+decisions}
    cache={};documents={};verified=[]
    try:
        for key in sorted({k for k,p in requested}):
            source=sources[key]
            if filehash(root/source['path'])!=source['sha256']:
                raise ValueError('BENCHMARK_ORIGINAL_SHA_MISMATCH: '+key)
            documents[key]=pymupdf.open(root/source['path'])
            verified.append(dict(source_key=key,source_sha256=source['sha256'],source_url=source['url'],
                                 physical_pages=sorted(p for k,p in requested if k==key)))
        for key,number in sorted(requested):
            page=documents[key][number-1];text=page.get_text(sort=True)
            rows=resource_rows(text,number,registry)+leach_tables(text,number,registry)+narrative_candidates(text,number,registry,parser_version=parser_version)
            tables=[]
            if any(c['kind']=='RESOURCE_TABLE_TOTAL' for c in rows):
                for i,t in enumerate(page.find_tables().tables):
                    tables.append(dict(physical_page=number,table_index=i,bbox=list(t.bbox),cells=t.extract(),header=t.header.names,external_header=t.header.external))
                positioned_resource_columns(rows,tables,text,registry,version='positioned-resource-columns-v3' if parser_version=='document-recognition-v3-bound-quantities' else 'positioned-resource-columns-v2')
            for c in rows:
                c['source_sha256']=sources[key]['sha256']
                c['issues']=sorted(set(c['issues']+candidate_value_issues(c)+
                    narrative_context_issues(c,dict(text=text),version=validation_version)))
            cache[(key,number)]=(rows,text)
    finally:
        for doc in documents.values():doc.close()
    cells=[];counts=Counter();scope_correct=unit_correct=located=accepted_n=0
    for case in numeric:
        rows,text=cache[(case['key'],case['page'])]
        found=[c for c in rows if re.search(case['row'],c['raw_text'],re.I)]
        accepted=[c for c in found if not c['issues']]
        row=accepted[0] if len(accepted)==1 else None
        values=({**row.get('values',{}),**{v['label']:v['value'] for v in row.get('extra_values',[])}} if row else {})
        scope_ok=bool(row and row.get('project_id')==projects[case['project']] and
                      row.get('resource_type')=='MINERAL_RESOURCE' and re.search(case['scope'],row.get('scope',''),re.I))
        for variable,expected in case['values'].items():
            actual=values.get(variable)
            actual_unit=(row.get('units',{}).get(variable) or next((v.get('unit') for v in row.get('extra_values',[]) if v['label']==variable),None)) if row else None
            locator_ok=bool(row and ' '.join(row['raw_text'].split()) in ' '.join(text.split()) and row['source_sha256'])
            correct=actual==expected and actual_unit==case['units'][variable] and scope_ok
            if correct:counts['true_positive']+=1;status='EXACT_VALUE_UNIT_SCOPE'
            elif actual is None:counts['false_negative']+=1;status='NOT_VALIDATED_LAYOUT_SCOPE_OR_BASIS'
            else:counts['false_positive']+=1;counts['false_negative']+=1;status='VALUE_UNIT_OR_SCOPE_ERROR'
            if actual is not None:
                accepted_n+=1;scope_correct+=scope_ok;unit_correct+=actual_unit==case['units'][variable];located+=locator_ok
            cells.append(dict(source_key=case['key'],source_sha256=sources[case['key']]['sha256'],physical_page=case['page'],
                              row_pattern=case['row'],variable=variable,expected=expected,actual=actual,
                              expected_unit=case['units'][variable],actual_unit=actual_unit,expected_scope=case['scope'],
                              actual_scope=row.get('scope') if row else None,scope_correct=scope_ok,source_locator_complete=locator_ok,
                              status=status,candidate_issues=[c['issues'] for c in found]))
    classification=[];confusion=Counter()
    for case in decisions:
        rows,text=cache[(case['key'],case['page'])]
        found=[c for c in rows if c['kind']==case['kind'] and re.search(case['pattern'],c['raw_text'],re.I)]
        accepted=[c for c in found if not c['issues'] and c.get('project_id')==projects[case['project']] and
                  (case['kind']!='RESOURCE_TABLE_TOTAL' or c.get('resource_type')=='MINERAL_RESOURCE')]
        if case.get('required_values'):
            accepted=[c for c in accepted if all(c.get('values',{}).get(k)==v for k,v in case['required_values'].items())]
        if case.get('forbidden_grade') is not None:
            accepted=[c for c in accepted if c.get('values',{}).get('grade')==case['forbidden_grade']]
        predicted=bool(accepted)
        category=('true_positive' if predicted else 'false_negative') if case['accept'] else ('false_positive' if predicted else 'true_negative')
        confusion[category]+=1
        classification.append(dict(label=case['label'],source_key=case['key'],source_sha256=sources[case['key']]['sha256'],
                                   physical_page=case['page'],pattern=case['pattern'],expected_acceptance=case['accept'],
                                   actual_acceptance=predicted,status=category.upper(),matched_candidates=len(found),
                                   issues=sorted({v for c in found for v in c['issues']}),
                                   required_values=case.get('required_values'),forbidden_grade=case.get('forbidden_grade')))
    def rates(c):
        tp,fp,fn=(c[k] for k in ('true_positive','false_positive','false_negative'))
        return dict(true_positive=tp,false_positive=fp,false_negative=fn,precision=tp/(tp+fp) if tp+fp else None,recall=tp/(tp+fn) if tp+fn else None)
    return dict(version='selected-original-page-benchmark-v4-column-controls',
                scope='PURPOSIVE_RENDERED_PAGE_SAMPLE_NOT_BLIND_HOLDOUT_OR_NATIONAL_ACCURACY',
                validation_version=validation_version,parser_version=parser_version,documents=len(documents),physical_pages=len(requested),
                numeric_cells=len(cells),numeric_metrics=dict(**rates(counts),
                    scope_accuracy_of_emitted=scope_correct/accepted_n if accepted_n else None,
                    unit_accuracy_of_emitted=unit_correct/accepted_n if accepted_n else None,
                    source_locator_completeness_of_emitted=located/accepted_n if accepted_n else None,emitted_cells=accepted_n),
                acceptance_cases=len(classification),acceptance_metrics=dict(**rates(confusion),true_negative=confusion['true_negative']),
                unit_contract='Printed Mt/percent/ppm; contained tonnes to kt only by explicit /1000. No element-to-oxide inference.',
                independence='Gold labels live only in this evaluator and are never imported into production ingestion. Existing Mt Weld/Browns/Koppamurra cases overlap prior benchmark; Yangibana, Cummins and semantic controls extend the sample. Not a blind held-out document test.',
                scope_metric_limit='Project ID and source table heading only; not a declaration of canonical resource scope, dyke equivalence, basis compatibility or formal JORC admission. Cummins Rare Dyke/Phos Dyke/Combined are identified by distinct original rows and cannot be summed.',
                cross_page_contract='Mt Weld pages2-3 share headers but are Resource/Reserve; Browns pages54-55 are different scopes. Header matching alone cannot establish continuation or authorize summing.',
                sources=verified,numeric_results=cells,acceptance_results=classification)


def evaluate_phase13(root):
    """Separate development set, additional document check and semantic controls.

    Additional pages were labelled after the initial general parser was frozen;
    these are a small non-blind document-disjoint check, not national accuracy.
    No benchmark labels are imported by production.
    """
    import re
    from au_ree_v2.pdf_extract import narrative_candidates,project_registry
    from au_ree_v2.store import filehash
    root=Path(root);version='document-recognition-v3-bound-quantities'
    development=evaluate_phase12(root,parser_version=version)
    numeric=[dict(key='salazar_mre2024',page=7,row=r'^TOTAL\s+230\b',project='salazar',scope=r'Salazar|Newmont',
        values=dict(ore_mt=230.,grade=1178.,Pr6O11=55.,Nd2O3=193.,Dy2O3=22.,Tb4O7=4.),
        units=dict(ore_mt='Mt',grade='ppm',Pr6O11='ppm',Nd2O3='ppm',Dy2O3='ppm',Tb4O7='ppm'))]
    decisions=[dict(label='kaolin_mass_not_bulk_TREO_resource',key='burracoppin_maiden2023',page=2,
        pattern=r'^TOTAL\s+62,751,000',kind='RESOURCE_TABLE_TOTAL',project='burracoppin',accept=False)]
    additional=evaluate_phase12(root,parser_version=version,numeric_cases=numeric,decision_cases=decisions)
    additional['scope']='DOCUMENT_DISJOINT_SMALL_POST_DEVELOPMENT_CHECK_NOT_BLIND_NATIONAL_VALIDATION'
    additional['independence']='Salazar and Burracoppin were not used in the Phase12 benchmark or to tune this column repair. Corpus was already available; this is not an independent human-labelled blind test.'
    sources={s['key']:s for s in json.loads((root/'data/manifest.json').read_text())['snapshots']}
    registry=project_registry(root);controls=[]
    for key,page,value in [('wudinna_mre2026',1,13.3),('mt_weld_2024',4,7.3),('mt_weld_2024',21,7.3)]:
        source=sources[key]
        if filehash(root/source['path'])!=source['sha256']:raise ValueError('BENCHMARK_ORIGINAL_SHA_MISMATCH')
        if source['kind']=='html':
            from au_ree_v2.evidence import html_text
            text=html_text(root,source)
        else:
            import pymupdf
            with pymupdf.open(root/source['path']) as doc:text=doc[page-1].get_text(sort=True)
        versions=[]
        for parser in ['document-recognition-v2-mineralogy',version]:
            candidates=narrative_candidates(text,page,registry,parser_version=parser)
            emitted=[c for c in candidates if any(n['value']==value and n.get('quantity_role') for n in c['numbers'])]
            versions.append(dict(parser_version=parser,false_extraction_candidates=len(emitted),
                                 raw_text=[c['raw_text'] for c in emitted]))
        controls.append(dict(source_key=key,source_sha256=source['sha256'],physical_page=page,value=value,
                             expected_extraction=False,results=versions))
    return dict(version='phase13-document-recovery-v1',baseline=evaluate_phase12(root),
                development_set=development,additional_documents=additional,semantic_controls=controls,
                limitation='Development recall and document-disjoint check reported separately; no pooled or national accuracy claim.')


if __name__=='__main__':
    result=evaluate_phase13('.') if '--phase13' in sys.argv else evaluate_phase12('.') if '--phase12' in sys.argv else evaluate('.',legacy='--phase9' in sys.argv)
    Path(sys.argv[1]).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('results','numeric_results','acceptance_results','sources')},indent=2))
