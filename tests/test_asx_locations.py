import copy
import json
import tempfile
import unittest
from pathlib import Path
from au_ree_v2.reviewed_locations import BASE, validate_locations, validate_location_target
from au_ree_v2.store import filehash


class NativeGAPoints(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.rows=[]
        self.meta=dict(spatialReference=dict(wkid=4283),description='Locations and status as at December 2025; https://pid.geoscience.gov.au/dataset/ga/150802')
        self.data=dict(spatialReference=dict(wkid=4283),features=[dict(attributes=dict(objectid=42,
            projectname='Brockman',state='WA',latitude=-18.32087,longitude=127.783709,status='Mineral deposit',
            commodities='Rare Earth Elements (REE)',source='Australian Critical Minerals Map 2025, 150802'),
            geometry=dict(x=127.783709,y=-18.32087))])
        self.cfg=dict(version='ga-native-project-location-v1',cutoff='2026-11-05',acquired_through='2026-11-10',
            effective_date='2025-12-31',date_precision='MONTH',effective_date_interval=['2025-12-01','2025-12-31'],
            service_metadata=self.capture('meta',BASE+'?f=pjson',self.meta),sources=dict(ga=self.capture('points',
                BASE+'/7/query?where=1%3D1&outFields=*&outSR=4283&returnGeometry=true&f=pjson',self.data)),
            reviews=[dict(project_id='P',review_id='location-P',objectid=42,source_key='ga',
                reviewed_project_name='Brockman Project',source_project_name='Brockman',state='WA',
                scope_match='NAMED_SINGLE_PROJECT_OR_DEPOSIT')])
        self.projects=[dict(entity_id='P',name='Brockman Project',aliases=['Brockman'])]

    def capture(self,key,url,data):
        p=self.root/(key+'.json');p.write_text(json.dumps(data),encoding='utf8');sha=filehash(p)
        self.rows[:]=[r for r in self.rows if r['url']!=url]
        self.rows.append(dict(url=url,document_sha256=sha,status='HTML_CAPTURED'))
        (self.root/'downloads.json').write_text(json.dumps(self.rows),encoding='utf8')
        return dict(asset_set='test',path=p.name,sha256=sha,url=url)

    def refresh(self):
        self.cfg['service_metadata']=self.capture('meta',BASE+'?f=pjson',self.meta)
        self.cfg['sources']['ga']=self.capture('points',self.cfg['sources']['ga']['url'],self.data)

    def run_review(self):
        p=self.root/'ledger.json';p.write_text(json.dumps(self.cfg),encoding='utf8')
        return validate_locations(p,{'test':self.root},self.projects,'2026-11-05')

    def test_named_paired_point_retains_native_datum_precision_and_currency(self):
        result=self.run_review();a=result['attributes']['P']
        self.assertEqual({'緯度':-18.3209,'經度':127.7837},{x['column']:x['value'] for x in a})
        scope=json.loads(a[0]['scope']);self.assertEqual('GDA94 / EPSG:4283',scope['crs'])
        self.assertIn('NOT_STATED',scope['positional_accuracy'])
        self.assertEqual('MONTH',result['receipts'][0]['date_precision'])
        self.assertIsNone(next(iter(result['sources'].values()))['publication_date'])
        self.assertTrue(all(x['column'] in ['緯度','經度'] for x in a))

    def test_hash_tampering_and_missing_receipt_rejected(self):
        (self.root/'points.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'HASH_OR_PATH'):self.run_review()
        self.refresh();(self.root/'downloads.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'RECEIPT'):self.run_review()

    def test_datum_currency_and_truncated_response_rejected(self):
        for field,value in [('spatialReference',{'wkid':4326}),('exceededTransferLimit',True),('error',{'message':'denied'})]:
            with self.subTest(field=field):
                old=copy.deepcopy(self.data);self.data[field]=value;self.refresh()
                with self.assertRaisesRegex(ValueError,'WRONG_CRS'):self.run_review()
                self.data=old
        self.meta['description']='Undated location map';self.refresh()
        with self.assertRaisesRegex(ValueError,'DATUM_OR_CURRENCY'):self.run_review()

    def test_only_official_public_query_profile_accepted(self):
        for url in [BASE.replace('services.ga.gov.au','example.org')+'/7/query?f=pjson',
                    BASE+'/7/query?where=1%3D1&outFields=*&outSR=4326&returnGeometry=true&f=pjson',
                    BASE+'/7/query?token=private&f=pjson']:
            with self.subTest(url=url):
                self.cfg['sources']['ga']['url']=url
                with self.assertRaisesRegex(ValueError,'OFFICIAL_FEATURE_URL'):self.run_review()

    def test_native_name_state_commodity_and_source_must_match(self):
        a=self.data['features'][0]['attributes'];original=copy.deepcopy(a)
        for key,value in [('projectname','Brockman Syncline'),('state','QLD'),('commodities','Iron ore'),('source','Unverified')]:
            with self.subTest(field=key):
                a.clear();a.update(original);a[key]=value;self.refresh()
                with self.assertRaisesRegex(ValueError,'NAME_STATE_COMMODITY_OR_SOURCE'):self.run_review()

    def test_bad_numbers_and_geometry_disagreement_rejected(self):
        original=copy.deepcopy(self.data)
        for v in [True,None,'-18.32087',float('nan'),20.0]:
            with self.subTest(latitude=v):
                self.data=copy.deepcopy(original);self.data['features'][0]['attributes']['latitude']=v;self.refresh()
                with self.assertRaisesRegex(ValueError,'COORDINATES|DISAGREEMENT'):self.run_review()
        self.data=copy.deepcopy(original);self.data['features'][0]['geometry']['x']=-18.32087;self.refresh()
        with self.assertRaisesRegex(ValueError,'DISAGREEMENT'):self.run_review()

    def test_duplicate_or_unknown_project_and_record_rejected(self):
        original=copy.deepcopy(self.cfg['reviews'])
        self.cfg['reviews']*=2
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):self.run_review()
        self.cfg['reviews']=original;self.cfg['reviews'][0]['project_id']='unknown'
        with self.assertRaisesRegex(ValueError,'PROJECT_OR'):self.run_review()
        self.cfg['reviews'][0]['project_id']='P';self.cfg['reviews'][0]['objectid']=99
        with self.assertRaisesRegex(ValueError,'UNIQUE_NATIVE_RECORD'):self.run_review()

    def test_combined_and_resource_subscope_cannot_borrow_parent_point(self):
        for name in ['Brockman — selected resource scope','Deep Leads – Rubble Mound – Wind Break REE Project']:
            with self.subTest(name=name):
                self.projects[0]['name']=name;self.cfg['reviews'][0]['reviewed_project_name']=name
                with self.assertRaisesRegex(ValueError,'COMPONENT_OR_RESOURCE_SCOPE'):self.run_review()

    def test_currency_cannot_become_exact_release_date(self):
        self.cfg['date_precision']='DAY'
        with self.assertRaisesRegex(ValueError,'CURRENCY_CONTRACT'):self.run_review()

    def test_target_pair_cannot_overwrite_or_cross_state_or_subscope(self):
        a=self.run_review()['attributes']['P'];row={'專案名稱':'Brockman Project','州省地區':'WA','緯度':'','經度':''}
        validate_location_target(row,a,{'WA':'WA'})
        for key,value,code in [('緯度','-18','OVERWRITE'),('經度','127','OVERWRITE'),('州省地區','QLD','STATE')]:
            with self.subTest(key=key):
                changed=dict(row,**{key:value})
                with self.assertRaisesRegex(ValueError,code):validate_location_target(changed,a,{'WA':'WA'})
        with self.assertRaisesRegex(ValueError,'SUBSCOPE'):validate_location_target(row,a,{'WA':'WA'},resource_subscope=True)
        with self.assertRaisesRegex(ValueError,'PAIR_REQUIRED'):validate_location_target(row,a[:1],{'WA':'WA'})


if __name__=='__main__':unittest.main()
