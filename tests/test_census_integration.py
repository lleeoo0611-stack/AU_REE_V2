import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from au_ree_v2.acquisition import census_acquisition, static_pdf_sources
from au_ree_v2.analysis import apply_census_cohort, write_csv
from au_ree_v2.census import census_selection
from au_ree_v2.evidence import retain_phase22_resource
from au_ree_v2.spatial import summary_locations
from au_ree_v2.store import digest, filehash


class CensusIntegrationTests(unittest.TestCase):
    def test_static_library_resolves_renamed_pdf_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            library=root/'library'
            library.mkdir()
            local=library/'renamed-document.PDF'
            local.write_bytes(b'%PDF-1.7\nlocal original')
            digest_pdf=filehash(local)
            (library/'unrelated.pdf').write_bytes(b'%PDF-1.7\nother original')
            phase22=root/'results/phase22-2026-11-06'
            phase22.mkdir(parents=True)
            (phase22/'snapshot_lock.json').write_text('[]',encoding='utf8')
            source=dict(key='asx-original',kind='pdf',publication_date='2026-11-08',
                        url='https://www.asx.com.au/document')
            after=dict(source,key='after-cutoff',publication_date='2026-11-14')
            denied=dict(source,key='disabled',enabled=False)
            registry={'sources':[source,after,denied]}
            claims={'evidence':[dict(source_key='asx-original',source_sha256=digest_pdf)]}
            with patch('au_ree_v2.acquisition.strict_dns_preflight') as dns:
                selected,receipts,_=census_acquisition(root,registry,root/'work',claims,
                    '2026-11-13',static_pdfs=[library])
            dns.assert_not_called()
            self.assertEqual(['asx-original'],[source['key'] for source in selected])
            self.assertEqual(digest_pdf,selected[0]['sha256'])
            self.assertEqual('STATIC_PDF_SHA_VERIFIED',receipts[0]['status'])

            # Two declarations for the same URL invalidate the shared binding.
            claims['evidence'].append(dict(source_key='after-cutoff',source_sha256='a'*64))
            selected,_,_=census_acquisition(root,registry,root/'work',claims,
                '2026-11-13',static_pdfs=[library])
            self.assertEqual([],selected)

    def test_reviewed_static_versions_keep_separate_bindings_for_the_same_url(self):
        with tempfile.TemporaryDirectory() as directory:
            library=Path(directory)
            sources=[]
            for index in range(2):
                path=library/f'version-{index}.pdf'
                path.write_bytes(f'%PDF-1.7\nversion {index}'.encode())
                sha=filehash(path)
                sources.append(dict(key=f'version-{index}',kind='pdf',enabled=False,
                    url='https://www.asx.com.au/document',publication_date='2026-11-08',
                    source_sha256=sha,reviewed_static_pdf_sha256=sha))
            registry={'sources':sources}
            claims={'evidence':[dict(source_key=s['key'],source_sha256=s['source_sha256']) for s in sources]}
            selected=static_pdf_sources(registry,claims,[library],'2026-11-13',set())
            self.assertEqual([(s['key'],s['source_sha256']) for s in sources],
                [(s['key'],s['sha256']) for s in selected])
            self.assertEqual([],static_pdf_sources(registry,claims,[library],'2026-11-07',set()))
            claims['evidence'].append(dict(source_key=sources[0]['key'],source_sha256=sources[1]['source_sha256']))
            with self.assertRaisesRegex(ValueError,'Static PDF pin conflicts'):
                static_pdf_sources(registry,claims,[library],'2026-11-13',set())

    def test_original_binding_survives_two_presentations_but_never_a_value_conflict(self):
        baseline=dict(source_sha='sha',date='2026-11-05',basis='TREO',ore_mt=2,grade_pct=1,
                      contained_treo_kt=20,scope='Whole resource',obs_ids=['ore','grade'])
        presentation=dict(baseline,scope='Published total',obs_ids=['alias-ore','alias-grade'])
        binding=tuple(baseline['obs_ids'])
        self.assertEqual(baseline,retain_phase22_resource([presentation,baseline],binding))
        changed=dict(presentation,grade_pct=2)
        self.assertIsNone(retain_phase22_resource([baseline,changed],binding))
        changed=dict(presentation,source_sha='other-sha')
        self.assertIsNone(retain_phase22_resource([baseline,changed],binding))

    def test_frozen_calculation_is_compatible_with_same_statement_reported_rounding(self):
        frozen=dict(statement_id='wolverine',scope='One resource',date='2025-01-15',basis='TREO',
            source_sha='frozen',ore_mt=7.3,grade_pct=0.96,contained_treo_kt=70.08,
            calculated_from_rounded_inputs_kt=70.08,rounding_bounds_kt=[69.2375,70.9275],
            obs_ids=['ore','grade'])
        report=dict(frozen,source_sha='same-statement-report',contained_treo_kt=70.5,
            obs_ids=['other-ore','other-grade','reported'])
        binding=tuple(frozen['obs_ids'])
        self.assertEqual(frozen,retain_phase22_resource([frozen,report],binding))
        for different in (dict(report,contained_treo_kt=72),dict(report,scope='Other scope'),
                          dict(report,statement_id='other'),dict(report,rounding_bounds_kt=[69,71])):
            with self.subTest(different=different):
                self.assertIsNone(retain_phase22_resource([frozen,different],binding))
        another=dict(report,source_sha='other-reported',contained_treo_kt=70.7)
        self.assertIsNone(retain_phase22_resource([frozen,report,another],binding))

    def test_reviewed_official_point_accepts_only_the_bound_census_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'layer.json'
            feature=dict(attributes=dict(objectid=7,projectname='Aileron',state='WA',
                source='https://doi.org/10.26186/150802',commodities='REE',longitude=128.4,latitude=-22.2),
                geometry=dict(x=128.4,y=-22.2))
            path.write_text(json.dumps(dict(spatialReference={'wkid':4283},features=[feature])),encoding='utf8')
            sha=filehash(path)
            case=dict(source_project_name='Aileron',state='WA')
            binding=dict(project_id='project',feature_id=7,rule='REVIEWED_POINT',binding=case)
            layer=dict(source_sha256=sha,summary_bindings=[binding])
            sources={sha:dict(resolved_path=str(path),url='https://example.invalid/official')}
            rules={'aliases.projects':[],'states':{'WA':'WA'},'ga_display_digits':4,'government_datasets':{}}
            row={'專案ID':'project','專案名稱':'Aileron Niobium–REE Project','州省地區':'WA'}
            self.assertEqual([],summary_locations(row,[],[layer],sources,rules,[]))
            case['census_project_name']=row['專案名稱']
            self.assertEqual({'緯度':-22.2,'經度':128.4},
                {r['column']:r['value'] for r in summary_locations(row,[],[layer],sources,rules,[])})
            self.assertEqual([],summary_locations(dict(row,專案名稱='Aileron West'),[],[layer],sources,rules,[]))
            binding['feature_id']=8
            self.assertEqual([],summary_locations(row,[],[layer],sources,rules,[]))

    def test_filter_uses_project_ids_and_gates_each_r_matrix(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            summary=out/'summary.csv'
            projects=[
                {'專案ID':'a','專案名稱':'Same name','州省地區':'WA','礦床型態代碼':'hard'},
                {'專案ID':'b','專案名稱':'Same name','州省地區':'SA','礦床型態代碼':'iac'},
                {'專案ID':'c','專案名稱':'Candidate','州省地區':'WA','礦床型態代碼':'hard'},
            ]
            write_csv(summary,projects,list(projects[0]))
            membership=[
                {'entity_id':'a','canonical_id':'a','kind':'PROJECT'},
                {'entity_id':'b','canonical_id':'b','kind':'PROJECT'},
                {'entity_id':'c','canonical_id':'c','kind':'SITE'},
            ]
            selected=census_selection(summary,membership,
                ['州省地區=WA','州省地區=SA','礦床型態代碼=hard'],out)
            self.assertEqual({'a'},selected)
            for panel in ('resource','qualified_cases'):
                write_csv(out/panel/'matrix.csv',
                    [{'project_id':pid,'R1':0.5} for pid in ('source-alias','b','c')],
                    ['project_id','R1'])
            prepared={'panels':{'resource':3,'qualified_cases':3}}
            apply_census_cohort(out,prepared,selected,{'source-alias':'a'})
            for panel,count in prepared['panels'].items():
                self.assertEqual(1,count)
                with (out/panel/'matrix.csv').open(encoding='utf8',newline='') as stream:
                    self.assertEqual(['source-alias'],[r['project_id'] for r in csv.DictReader(stream)])
            with self.assertRaisesRegex(ValueError,'Invalid census filter'):
                census_selection(summary,membership,['not_a_column=x'],out)

    def test_replay_pins_source_bytes_and_preserves_frozen_phase22_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def source(key,file,date):
                path=root/file
                path.write_text(file,encoding='utf8')
                return dict(key=key,kind='html',path=file,sha256=filehash(path),
                            publication_date=date,available_date=date)

            old=source('same-key','phase22.html','2026-11-05')
            changed=source('same-key','newer.html','2026-11-13')
            added=source('asx-added','asx.html','2026-11-10')
            phase22=root/'results/phase22-2026-11-06'
            phase22.mkdir(parents=True)
            (phase22/'snapshot_lock.json').write_text(json.dumps([old]),encoding='utf8')
            registry={'sources':[changed,added]}
            replay=root/'replay.json'
            replay.write_text(json.dumps(dict(cutoff='2026-11-13',registry_sha256=digest(registry),
                snapshots=[changed,added],outcomes=[])),encoding='utf8')
            selected,_,decisions=census_acquisition(root,registry,root/'work',{},'2026-11-13',replay)
            self.assertEqual([old,added],selected)
            self.assertEqual(['FROZEN_PHASE22_VERSION_RETAINED','ASX_SOURCE_ADDED'],
                             [row['action'] for row in decisions])
            (root/'asx.html').write_text('changed bytes',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                census_acquisition(root,registry,root/'work',{},'2026-11-13',replay)
