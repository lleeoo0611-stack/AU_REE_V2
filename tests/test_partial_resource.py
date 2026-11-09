"""Synthetic native-source tests. No external network or private source fixture."""
import copy
import csv
import json
import math
import re
import tempfile
import unittest
from pathlib import Path

import pymupdf

from au_ree_v2.asx_validation import validate_reviews
from au_ree_v2.partial_resource import MODE, REASON, WITHHELD_COLUMNS
from au_ree_v2.project_summary import resource_bundle, complete_sum, HEAVY, export_summary
from au_ree_v2.store import canonical, connect, entity, filehash

GRADES = dict(La2O3=223, Pr6O11=49, Nd2O3=166, Sm2O3=29, Eu2O3=4, Gd2O3=23,
              Tb4O7=3, Dy2O3=21, Ho2O3=4, Er2O3=11, Tm2O3=2, Yb2O3=10, Lu2O3=1, Y2O3=113)


def box(page, text):
    r = page.search_for(text)[0]
    return [r.x0 - .2, r.y0 - .2, r.x1 + .2, r.y1 + .2]


class PartialResourceRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); (self.root / 'data').mkdir()
        self.pdf = self.root / 'data/source.pdf'; self.scope = 'Splinter Inferred only; 500 ppm TREO+Y2O3 cutoff'
        d = pymupdf.open(); p = d.new_page()
        p.insert_text((50, 50), 'ASX Announcement\n16 January 2025\nMock Project', fontsize=10)
        issue_box = box(p, '16 January 2025')
        p = d.new_page(width=1500, height=400)
        p.insert_text((30, 45), 'Table 35. Splinter Mineral Resource estimates', fontsize=10)
        p.insert_text((30, 65), 'Splinter Inferred resource as at 15 January 2025', fontsize=10)
        p.insert_text((40, 95), 'Cut off', fontsize=8); p.insert_text((40, 110), 'TREO+Y2O3', fontsize=8)
        p.insert_text((145, 100), 'Class', fontsize=8)
        locations = [('Tonnes', 235), ('Ce2O3', 320)] + [(e, 400 + i * 65) for i, e in enumerate(GRADES)]
        for label, x in locations:
            p.insert_text((x, 100), label, fontsize=8)
            p.insert_text((x, 115), "'000 t" if label == 'Tonnes' else 'ppm', fontsize=8)
        p.insert_text((50, 205), '500', fontsize=8)
        for label, y in [('Inferred', 185), ('Unclassified', 205), ('Total', 225)]:
            p.insert_text((145, y), label, fontsize=8)
        for label, x in locations:
            v = '22,849' if label == 'Tonnes' else '397' if label == 'Ce2O3' else str(GRADES[label])
            p.insert_text((x, 185), v, fontsize=8)
            p.insert_text((x, 205), '999', fontsize=8); p.insert_text((x, 225), '888', fontsize=8)
        table = [25, 30, 1450, 300]; row = [25, 173, 1450, 190]
        section = dict(page=2, bbox=table, anchor='Splinter Inferred resource as at 15 January 2025',
                       anchor_bbox=box(p, 'Splinter Inferred resource as at 15 January 2025'), row_label='Inferred',
                       cutoff_group=dict(bbox=[25, 173, 1450, 230], label='500', label_bbox=box(p, '500'),
                                         column_bbox=[30, 80, 115, 300], header_label='Cut off TREO+Y2O3',
                                         header_bbox=[39, 85, 108, 113]))
        observations = []
        for label, x in locations:
            if label == 'Ce2O3': continue
            ore = label == 'Tonnes'; variable = 'ore_mt' if ore else 'reported_resource_' + re.match(r'[A-Z][a-z]?', label)[0].lower() + '_ppm'
            binding = dict(mode='native_cell', field=variable, scope=self.scope, page=2, section_id='splinter500',
                table_bbox=table, table_label='Table 35. Splinter Mineral Resource estimates', table_label_bbox=box(p, 'Table 35. Splinter Mineral Resource estimates'),
                scope_anchor='Splinter Inferred resource as at 15 January 2025', scope_anchor_bbox=section['anchor_bbox'],
                row_bbox=row, row_label='Inferred')
            # Locate the class label, not the same word in the section heading.
            r=p.search_for('Inferred')[1];binding['row_label_bbox']=[r.x0-.2,r.y0-.2,r.x1+.2,r.y1+.2]
            binding.update(column_bbox=[x-3, 80, x+58, 300],column_label=label,column_label_bbox=next([r.x0-.2,r.y0-.2,r.x1+.2,r.y1+.2] for r in p.search_for(label) if abs(r.x0-x)<1),
                           original_unit='kt' if ore else 'ppm', unit_bbox=box(p,"'000 t") if ore else [x-.2,105.5,x+16,118],
                           unit_label="'000 t" if ore else 'ppm')
            if not ore: binding['basis']=label
            observations.append(dict(variable=variable, value=22.849 if ore else GRADES[label], unit='Mt' if ore else 'ppm',
                                     original_unit='kt' if ore else 'ppm', basis='TREO' if ore else label,
                                     original_token='22,849' if ore else str(GRADES[label]),
                                     evidence=dict(page=2,markers=['Table 35.','Inferred']),cell_binding=binding))
        cerium_header = box(p, 'Ce2O3')
        p = d.new_page();p.insert_text((50,50),'Conversion factors were applied for resource reporting.',fontsize=10)
        p.insert_text((50,90),'Table 33. Factors used to convert elements to oxides.',fontsize=10)
        p.insert_text((70,120),'Cerium',fontsize=10);p.insert_text((170,120),'Ce2O3',fontsize=10);p.insert_text((250,120),'1.171',fontsize=10)
        proof = dict(kind='NATIVE_ELEMENT_TO_OXIDE_ROW',page=3,table_bbox=[45,75,350,150],
                     table_label='Table 33. Factors used to convert elements to oxides.',
                     table_label_bbox=box(p,'Table 33. Factors used to convert elements to oxides.'),row_bbox=[65,108,285,124],conversion_factor=1.171,
                     evidence=dict(page=3,markers=['resource reporting','Ce2O3','1.171']))
        d.save(self.pdf);d.close()
        self.review=dict(review_id='partial-fixture',source_key='partial-fixture',project_id='P',source_sha256=filehash(self.pdf),
            asset_set='fixture',path='data/source.pdf',url='https://example.test/public-report.pdf',publication_date='2025-01-16',
            effective_date='2025-01-15',effective_date_role='RESOURCE_EFFECTIVE_DATE',date_precision='DAY',
            identity_evidence=dict(page=1,markers=['Mock Project']),date_evidence=dict(page=2,markers=['15 January 2025']),
            scope_evidence=[dict(page=2,markers=['Mineral Resource','Inferred'])],scope=self.scope,statement_id='splinter500',
            resource_categories=['INFERRED'],selection_reason='Selected Inferred only at 500 ppm; unclassified and totals excluded.',
            selected_resource_sections=dict(splinter500=section), observations=observations,
            partial_resource_projection=dict(mode=MODE,withholding_reason=REASON,source_species='Ce2O3',canonical_species='CeO2',
                                             basis_proof=proof,resource_header=dict(page=2,bbox=cerium_header,section_id='splinter500')))
        self.issue_box=issue_box
        self.projects=[dict(entity_id='P',name='Mock Project',aliases=['Mock Project'])]
        (self.root/'downloads.json').write_text(canonical([dict(url=self.review['url'],document_sha256=self.review['source_sha256'],status='PDF_ACQUIRED')]))

    def validate(self, review=None):
        r=self.review if review is None else review
        path=self.root/'reviews.json';path.write_text(canonical(dict(version='asx-source-review-v2',acquired_through='2026-11-09',reviews=[r])))
        return validate_reviews(path,{'fixture':self.root},self.projects)

    def technical_report(self):
        r=copy.deepcopy(self.review)
        r.update(effective_date='2025-01-16',effective_date_role='TECHNICAL_REPORT_RESOURCE_AS_REPORTED',
                 publication_date_role='TECHNICAL_REPORT_ISSUE_DATE_NOT_RELEASE',source_kind='PUBLIC_ARCHIVED_TECHNICAL_REPORT',
                 resource_effective_date_unknown=True,public_release_date_unknown=True,document_issue_date='2025-01-16',
                 document_issue_evidence=dict(page=1,markers=['16 January 2025'],bbox=self.issue_box,text='16 January 2025'),
                 date_evidence=dict(page=1,markers=['16 January 2025']))
        return r

    def validated_bundle(self):
        result=self.validate();rows=result['observations']['P'];contract=result['partial_resource_contracts']['P']
        bundle, reason=resource_bundle(rows,partial_resource=contract)
        self.assertIsNotNone(bundle,reason)
        return rows,contract,bundle

    def test_native_ore_and_14_oxides_validate_without_treo(self):
        rows,contract,bundle=self.validated_bundle()
        self.assertEqual(15,len(rows));self.assertEqual({'ore_mt':22.849},bundle['value'])
        self.assertNotIn('magnet_reo_share_pct',{o['variable'] for o in rows})
        values={o['basis']:o['value']*22.849*.001 for o in rows if o['basis'] in GRADES}
        self.assertAlmostEqual(4.912535,complete_sum(values,('Nd2O3','Pr6O11')))
        self.assertAlmostEqual(3.770085,complete_sum(values,HEAVY))
        self.assertNotIn('CeO2',values)

    def test_absent_flag_keeps_required_pair(self):
        r=copy.deepcopy(self.review);r.pop('partial_resource_projection')
        with self.assertRaisesRegex(ValueError,'REVIEW_RESOURCE_BUNDLE_'):self.validate(r)

    def test_projection_without_explicit_contract_does_not_fallback(self):
        rows,contract,_=self.validated_bundle()
        grade=dict(rows[0],variable='grade',value=1056,unit='ppm')
        self.assertIsNone(resource_bundle(rows+[grade])[0])
        self.assertEqual('PARTIAL_RESOURCE_OPT_IN_REQUIRED',resource_bundle(rows)[1])

    def test_false_flag_is_not_opt_in(self):
        for flag in [False,True,None,{},dict(mode=MODE)]:
            with self.subTest(flag=flag):
                r=copy.deepcopy(self.review);r['partial_resource_projection']=flag
                with self.assertRaisesRegex(ValueError,'EXPLICIT_MODE_AND_REASON'):self.validate(r)

    def test_grade_total_and_ceo2_are_forbidden(self):
        for variable,basis,unit,value in [('grade','TREO','ppm',1056),('contained_treo_kt','TREO','kt TREO',24.128544),('reported_resource_ce_ppm','CeO2','ppm',397)]:
            r=copy.deepcopy(self.review);r['observations'].append(dict(r['observations'][0],variable=variable,basis=basis,unit=unit,value=value))
            with self.subTest(variable=variable),self.assertRaisesRegex(ValueError,'TOTAL_GRADE_RATIO_OR_CERIUM_FORBIDDEN'):self.validate(r)

    def test_normalization_is_not_a_partial_projection(self):
        for key,value in [('bulk_treo_grade_pct',dict(value=.1056)),('bulk_hm_percent',dict(value=10))]:
            r=copy.deepcopy(self.review);r[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'NORMALIZATION_FORBIDDEN'):self.validate(r)
        for unit in ['%TREO','%HM','%']:
            r=copy.deepcopy(self.review);r['observations'][1]['original_unit']=unit
            with self.subTest(unit=unit),self.assertRaisesRegex(ValueError,'DIRECT_BULK_OXIDE_PPM_REQUIRED'):self.validate(r)

    def test_all_four_contract_dimensions_are_enforced(self):
        for key in ['scope','statement_id','source_sha256','effective_date']:
            r=copy.deepcopy(self.review);r['observations'][1][key]='different'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'OBSERVATION_CONTRACT_MISMATCH'):self.validate(r)
        rows,contract,_=self.validated_bundle()
        for key in ['scope','statement_id','source_sha','effective_date']:
            changed=copy.deepcopy(rows);changed[1][key]='different'
            with self.subTest(bundle_key=key):
                self.assertEqual('PARTIAL_RESOURCE_EXACT_CONTRACT_REQUIRED',resource_bundle(changed,partial_resource=contract)[1])

    def test_cross_section_and_wrong_source_header_rejected(self):
        r=copy.deepcopy(self.review);r['observations'][1]['cell_binding']['section_id']='other'
        with self.assertRaisesRegex(ValueError,'SELECTED_RESOURCE_SECTION_MISMATCH'):self.validate(r)
        r=copy.deepcopy(self.review);r['partial_resource_projection']['resource_header']['bbox']=[390,85,458,103]
        with self.assertRaisesRegex(ValueError,'CERIUM_HEADER_MISMATCH'):self.validate(r)

    def test_partial_does_not_use_upstream_grouped_magnet_path(self):
        from au_ree_v2.project_summary import reported_magnet_group
        rows,contract,bundle=self.validated_bundle()
        group=dict(rows[1],variable='reported_resource_magnet_ppm',basis='PrNdDyTb_OXIDES',value=239)
        self.assertIsNone(reported_magnet_group(rows+[group],bundle))
        self.assertIsNone(resource_bundle(rows+[group],partial_resource=contract)[0])
        r=copy.deepcopy(self.review)
        r['observations'].append(dict(r['observations'][1],variable='reported_resource_magnet_ppm',basis='PrNdDyTb_OXIDES',value=239))
        with self.assertRaisesRegex(ValueError,'GROUPED_OXIDES_FORBIDDEN'):self.validate(r)

    def test_native_basis_proof_not_just_declared_reason(self):
        for mutation in ['missing','wrong-row','wrong-page','wrong-factor','wrong-table','missing-context']:
            r=copy.deepcopy(self.review);p=r['partial_resource_projection']['basis_proof']
            if mutation=='missing':r['partial_resource_projection'].pop('basis_proof')
            if mutation=='wrong-row':p['row_bbox']=[65,128,285,144]
            if mutation=='wrong-page':p['page']=2
            if mutation=='wrong-factor':p['conversion_factor']=1.228
            if mutation=='wrong-table':p['table_label']='A random table'
            if mutation=='missing-context':p['evidence']['markers']=['not in report']
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.validate(r)

    def test_unverified_contract_and_raw_relabelling_rejected(self):
        rows,contract,_=self.validated_bundle();bad=copy.deepcopy(contract);bad['basis_proof_verified']=False
        self.assertIsNone(resource_bundle(rows,partial_resource=bad)[0])
        rows[1]['raw']='{}'
        self.assertEqual('PARTIAL_RESOURCE_INPUT_PROVENANCE_REQUIRED',resource_bundle(rows,partial_resource=contract)[1])

    def test_no_unknown_as_zero_missing_nd_or_y(self):
        rows,contract,_=self.validated_bundle()
        for missing,required in [('Nd2O3',('Nd2O3','Pr6O11')),('Y2O3',HEAVY)]:
            partial=[o for o in rows if o['basis']!=missing]
            bundle,_=resource_bundle(partial,partial_resource=contract)
            self.assertIsNotNone(bundle)
            elements={o['basis']:o['value']*22.849*.001 for o in partial if o['basis'] in GRADES}
            self.assertIsNone(complete_sum(elements,required));self.assertNotIn(missing,elements)
        self.assertEqual(0,complete_sum({e:0 for e in HEAVY},HEAVY))

    def test_invalid_or_conflicting_values_fail_closed(self):
        rows,contract,_=self.validated_bundle()
        for value in [None,True,float('nan'),float('inf'),-1,1000001]:
            changed=copy.deepcopy(rows);changed[1]['value']=value
            with self.subTest(value=value):self.assertIsNone(resource_bundle(changed,partial_resource=contract)[0])
        for idx in [0,1]:
            changed=copy.deepcopy(rows);changed.append(dict(changed[idx],value=changed[idx]['value']+1))
            self.assertEqual('PARTIAL_RESOURCE_CONFLICTING_INPUTS',resource_bundle(changed,partial_resource=contract)[1])

    def test_no_ore_no_projection(self):
        rows,contract,_=self.validated_bundle()
        self.assertEqual('PARTIAL_RESOURCE_ORE_AND_OXIDES_REQUIRED',resource_bundle(rows[1:],partial_resource=contract)[1])

    def test_cutoff_group_exact_class_and_label_required(self):
        for mutation in ['wrong-label','huge-group','wrong-class','outside-group']:
            r=copy.deepcopy(self.review);s=r['selected_resource_sections']['splinter500']
            if mutation=='wrong-label':s['cutoff_group']['label']='400'
            if mutation=='huge-group':s['cutoff_group']['bbox']=[25,200,1450,230]
            if mutation=='wrong-class':s['row_label']='Total'
            if mutation=='outside-group':r['observations'][0]['cell_binding']['row_bbox']=[25,193,1450,210]
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'REVIEW_CELL_'):self.validate(r)

    def test_partial_requires_cutoff_group_proof(self):
        r=copy.deepcopy(self.review);r['selected_resource_sections']['splinter500'].pop('cutoff_group')
        with self.assertRaisesRegex(ValueError,'SELECTED_RESOURCE_CUTOFF_GROUP_REQUIRED'):self.validate(r)

    def test_context_only_partial_cannot_become_fallback(self):
        r=copy.deepcopy(self.review);r.update(resource_selection_role='CONTEXT_ONLY',context_selection_reason='Nonselected evidence only')
        result=self.validate(r)
        self.assertFalse(result['observations']);self.assertFalse(result['partial_resource_contracts'])
        self.assertFalse(result['resource_preferences'])

    def test_unclassified_and_combined_total_rows_are_not_inferred(self):
        for y,label in [(205,'Unclassified'),(225,'Total')]:
            r=copy.deepcopy(self.review)
            with pymupdf.open(self.pdf) as d:
                region=box(d[1],label)
            for o in r['observations']:
                o['cell_binding'].update(row_bbox=[25,y-12,1450,y+5],row_label=label,row_label_bbox=region)
            with self.subTest(label=label),self.assertRaisesRegex(ValueError,'RESOURCE_TOTAL_ROW_REQUIRED'):self.validate(r)

    def test_technical_report_date_exposes_unknown_dates(self):
        r=self.technical_report();result=self.validate(r);receipt=result['receipts'][0]
        self.assertEqual('TECHNICAL_REPORT_RESOURCE_AS_REPORTED',receipt['effective_date_role'])
        self.assertTrue(receipt['resource_effective_date_unknown']);self.assertTrue(receipt['public_release_date_unknown'])
        self.assertEqual('TECHNICAL_REPORT_ISSUE_DATE_NOT_RELEASE',receipt['publication_date_role'])

    def test_technical_report_date_requires_every_disclosure(self):
        for key in ['source_kind','publication_date_role','resource_effective_date_unknown','public_release_date_unknown','document_issue_date','partial_resource_projection']:
            r=self.technical_report();r.pop(key)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'TECHNICAL_REPORT_DATE_CONTRACT'):self.validate(r)
        r=self.technical_report();r['document_issue_evidence']['text']='15 January 2025'
        with self.assertRaisesRegex(ValueError,'DOCUMENT_ISSUE_DATE_MISMATCH'):self.validate(r)
        r=self.technical_report();r['study']={'scale':'PFS_MODEL'}
        with self.assertRaisesRegex(ValueError,'TECHNICAL_REPORT_DATE_CONTRACT'):self.validate(r)

    def export(self, review=None):
        r=self.review if review is None else review
        run=self.root/'run';run.mkdir();out=self.root/'export';database=self.root/'canonical.sqlite'
        source=dict(key='partial-fixture',kind='pdf',path='data/source.pdf',sha256=filehash(self.pdf),url=r['url'],publication_date=r['publication_date'],available_date='2025-01-16')
        claims=dict(projects=[dict(id='demo',name='Mock Project',identity_source='partial-fixture',observations=[])])
        cp=self.root/'data/claims.json';cp.write_text(canonical(claims))
        (run/'snapshot_lock.json').write_text(canonical([source]));(run/'configuration.json').write_text(canonical(dict(claims_sha256=filehash(cp),research={})))
        db=connect(database);pid=entity(db,'project_registry_v1','demo','PROJECT')
        db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)',(source['sha256'],source['key'],source['url'],source['publication_date'],source['available_date'],source['path'],'pdf','{}'))
        db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)',(pid,source['sha256'],'Mock Project','WA',None,None,None,None,'{}'))
        db.commit();db.close();before=filehash(database)
        r['project_id']=pid;self.projects[0]['entity_id']=pid;self.validate(r)
        result=export_summary(self.root,database,run,out,review_ledger=self.root/'reviews.json',asset_roots={'fixture':self.root})
        self.assertEqual(before,filehash(database))
        with (out/'專案總表.csv').open(encoding='utf-8-sig') as f:row=next(csv.DictReader(f))
        with (out/'field_provenance.csv').open(encoding='utf-8-sig') as f:trace=list(csv.DictReader(f))
        with (out/'missing_fields.csv').open(encoding='utf-8-sig') as f:gaps=list(csv.DictReader(f))
        return result,row,trace,gaps

    def test_export_partial_never_promotes_treo_pair_and_ratios(self):
        result,row,trace,gaps=self.export(self.technical_report())
        self.assertEqual('22.849',row['礦石蘊藏量_Mt']);self.assertEqual('14',row['已公布元素數_共15項'])
        self.assertAlmostEqual(4.912535,float(row['NdPr蘊藏量_kt_需兩者皆公布']))
        self.assertAlmostEqual(3.770085,float(row['完整重稀土組合蘊藏量_kt_需8元素皆公布']))
        for column in WITHHELD_COLUMNS:self.assertEqual('',row[column],column)
        self.assertEqual('是',row['四項磁性元素皆公布']);self.assertEqual(0,result['filled_counts']['有TREO資源估計'])
        self.assertEqual(WITHHELD_COLUMNS,{g['column'] for g in gaps if g['reason']==REASON})
        ore=next(t for t in trace if t['column']=='礦石蘊藏量_Mt')
        self.assertEqual('True',ore['resource_effective_date_unknown']);self.assertEqual('True',ore['public_release_date_unknown'])
        self.assertEqual('TECHNICAL_REPORT_ISSUE_DATE_NOT_RELEASE',ore['publication_date_role'])
        self.assertIn('Ce2O3',row['元素數據一致性檢查'])

    def test_export_incomplete_heavy_remains_blank(self):
        r=copy.deepcopy(self.review);r['observations']=[o for o in r['observations'] if o['basis']!='Y2O3']
        _,row,_,_=self.export(r)
        self.assertEqual('',row['完整重稀土組合蘊藏量_kt_需8元素皆公布'])
        self.assertEqual('',row['Y2O3_氧化釔_kt']);self.assertEqual('13',row['已公布元素數_共15項'])


if __name__=='__main__': unittest.main()
