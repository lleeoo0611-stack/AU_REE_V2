import copy,json,tempfile,unittest
from pathlib import Path
import pymupdf
from au_ree_v2.reviewed_discovery import validate_discovery
from au_ree_v2.store import filehash


class NamedProjectLocationBridge(unittest.TestCase):
    def test_location_retains_its_own_original_and_rejects_cross_project_joins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,pages in [('identity',['Signed 1 January 2023\nDemo Project\nDemo Limited']),
                               ('location',['ASX Announcement\n31 December 2022\nDemo Project in Western Australia\nDemo Limited',
                                            'Other Project in Western Australia\nDemo Limited'])]:
                doc=pymupdf.open()
                for text in pages:doc.new_page().insert_text((40,40),text)
                doc.save(root/(name+'.pdf'));doc.close()
            sources=[dict(asset_set='test',path=name+'.pdf',sha256=filehash(root/(name+'.pdf')),kind='pdf',url=url,
                          evidence=[dict(page=1,markers=[marker])]) for name,url,marker in [
                ('identity','https://announcements.asx.com.au/asxpdf/20230102/pdf/abc.pdf','Demo Project'),
                ('location','https://announcements.asx.com.au/asxpdf/20221231/pdf/def.pdf','Demo Project')]]
            identity=dict(source_index=0,source_key='identity',publication_date='2023-01-02',document_issue_date='2023-01-01',
                date_evidence_role='DOCUMENT_ISSUE_DATE_WITH_ASX_URL_RELEASE_DATE',publication_date_role='ASX_DATED_URL',
                date_evidence=dict(page=1,markers=['Signed 1 January 2023']),project_evidence=dict(page=1,markers=['Demo Project']),
                name_marker='Demo Project',state='WA',state_marker='Western Australia',developer=dict(value='Demo Limited',evidence=dict(page=1,markers=['Demo Limited'])),
                state_bridge=dict(mode='DATED_ASX_SAME_PROJECT_AND_ISSUER_STATE_ONLY',source_index=1,source_key='state',issuer_marker='Demo',project_evidence=dict(page=1,markers=['Demo Project','Western Australia'])))
            candidate=dict(candidate_key='demo',name='Demo Project',aliases=[],decision='ADMIT_PROJECT',reason='Test',country='AU',scope='Historical location only',sources=sources,identity=identity)
            config=dict(version='reviewed-project-discovery-v1',cutoff='2026-11-05',acquired_through='2026-11-10',candidates=[candidate])
            def check(cfg):
                rows=cfg['candidates'][0]['sources']
                (root/'downloads.json').write_text(json.dumps([dict(url=s['url'],document_sha256=s['sha256'],status='PDF_ACQUIRED') for s in rows]))
                ledger=root/'ledger.json';ledger.write_text(json.dumps(cfg))
                return validate_discovery(ledger,{'test':root},[],'2026-11-05')
            result=check(config)
            self.assertIsNone(result['records'][0]['state'])
            self.assertEqual('WA',result['records'][1]['state'])
            self.assertEqual(sources[1]['sha256'],result['records'][1]['source_sha'])
            self.assertEqual({},result['deferred_fields'][result['projects'][0]['entity_id']])
            for case in ['wrong_project','wrong_issuer','wrong_state','primary_source','future_url','non_asx','unmatched_header','no_bridge','tampered_hash']:
                c=copy.deepcopy(config);r=c['candidates'][0];i=r['identity'];b=i['state_bridge']
                if case=='wrong_project':b['project_evidence']=dict(page=2,markers=['Other Project'])
                if case=='wrong_issuer':b['issuer_marker']='Other'
                if case=='wrong_state':i.update(state='SA',state_marker='South Australia')
                if case=='primary_source':b['source_index']=0
                if case=='future_url':r['sources'][1]['url']='https://announcements.asx.com.au/asxpdf/20240101/pdf/def.pdf'
                if case=='non_asx':r['sources'][1]['url']='https://example.com/asxpdf/20221231/pdf/def.pdf'
                if case=='unmatched_header':r['sources'][1]['url']='https://announcements.asx.com.au/asxpdf/20221230/pdf/def.pdf'
                if case=='no_bridge':i.pop('state_bridge')
                if case=='tampered_hash':r['sources'][1]['sha256']='0'*64
                with self.subTest(case=case),self.assertRaises(ValueError):check(c)
