import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from au_ree_v2.official_location_adapters import *

ROOT=Path(__file__).resolve().parents[1]
def decision(dataset):
    d=proposed_decisions();next(x for x in d if x['scope']['dataset']==dataset)['decided_by']='fixture researcher';return d

def wa(name='Example Project'):
    return {'attributes':{'site_code':1,'site_title':name,'commodity':'Rare Earth Elements',
        'longitude':120.0,'latitude':-25.0,'point_conf':'Approximate','extract_da':'2026-10-01'}}
R={'sha256':'a'*64,'url':DATASETS['WA_MINEDEX']['url']+'/query','acquired_at':'2026-11-11T00:00:00+00:00','source_version':'fixture'}
ROW={'專案ID':'test','專案名稱':'Example Deposit','州省地區':'西澳大利亞州','緯度':'','經度':''}

class OfficialLocationTests(unittest.TestCase):
    def test_unapproved_no_transport_or_directory(self):
        f=Mock(side_effect=AssertionError('network'))
        with tempfile.TemporaryDirectory() as tmp:
            for dataset in DATASETS:
                result=acquire_dataset(dataset,proposed_decisions(),Path(tmp)/'absent',fetch=f)
                self.assertEqual(result['network_requests'],0)
            self.assertFalse((Path(tmp)/'absent').exists());f.assert_not_called()
    def test_whitespace_decision_is_unapproved(self):
        d=decision('WA_MINEDEX');next(x for x in d if x['scope']['dataset']=='WA_MINEDEX')['decided_by']='  '
        self.assertIsNone(decision_for('WA_MINEDEX',d))
    def test_wa_identity_crs(self):
        c=normalize_feature('WA_MINEDEX',wa(),R)
        self.assertEqual((c['longitude'],c['latitude']),(120,-25));self.assertEqual(c['accuracy'],'Approximate')
        self.assertEqual(c['accuracy_unit'],'SOURCE_TEXT_NOT_METRES')
    def test_gda94_reference_transformation(self):
        # Frozen fixture from installed EPSG GDA94 to GDA2020 (1), coordinate-frame Helmert.
        f={'properties':{'ENO':1,'OCCURRENCE_NAME':'Example','COMMODITY_NAMES':'REE','STATE':'WA','LONG_GDA94':120,'LAT_GDA94':-25,'ACCURACY_M':100}}
        c=normalize_feature('GA_OZMIN',f,R)
        self.assertAlmostEqual(c['longitude'],120.0000097695878,places=9)
        self.assertAlmostEqual(c['latitude'],-24.999986377628897,places=9)
    def test_qld_uses_attributes_never_mercator_geometry(self):
        f={'attributes':{'site_no':1,'occur_name':'Example','all_commodities':'monazite','longitude':145,'latitude':-20,'loc_accuracy':100},'geometry':{'x':0,'y':0,'spatialReference':{'wkid':3857}}}
        c=normalize_feature('QLD_MINOCC',f,R)
        self.assertAlmostEqual(c['longitude'],145,places=4);self.assertEqual(c['original_crs'],'EPSG:4283')
        del f['attributes']['longitude']
        with self.assertRaisesRegex(ValueError,'PAIR_REQUIRED'):normalize_feature('QLD_MINOCC',f,R)
    def test_nsw_conflicting_datum_rejected(self):
        f={'properties':{'occurrence_id':1,'deposit_name':'Example','major_comm':'REE','longda94':145,'latgda94':-30,'ll_coordsys':'AGD66'}}
        with self.assertRaisesRegex(ValueError,'DATUM_CONFLICT'):normalize_feature('NSW_MINVIEW',f,R)
    def test_sa_identity_crs(self):
        f={'properties':{'MINERAL_DEPOSIT_NO':1,'DEPOSIT_NAME':'Example','DEPOSIT_COMMODITIES':'xenotime','LONGITUDE':135,'LATITUDE':-30,'HORIZ_ACCURACY':'unknown'}}
        c=normalize_feature('SA_SARIG',f,R);self.assertEqual(c['longitude'],135);self.assertEqual(c['accuracy'],'unknown')
    def test_wrong_state_rejected(self):
        c=normalize_feature('WA_MINEDEX',wa(),R);c['state']='QLD'
        self.assertEqual(match_project(ROW,[c])['status'],'STATE_MISMATCH')
    def test_multiple_candidates_review(self):
        c=normalize_feature('WA_MINEDEX',wa(),R)
        self.assertEqual(match_project(ROW,[c,c])['status'],'MULTIPLE_CANDIDATES')
    def test_distant_and_fuzzy_review(self):
        c=normalize_feature('WA_MINEDEX',wa(),R)
        self.assertEqual(match_project(ROW,[c],reference=(130,-25),max_distance_m=10000)['status'],'DISTANT_FROM_VERIFIED_REFERENCE')
        c['names']=['Examples'];self.assertEqual(match_project(ROW,[c])['status'],'NO_EXACT_NAME_MATCH')
    def test_pair_no_overwrite(self):
        c=normalize_feature('WA_MINEDEX',wa(),R);d=decision('WA_MINEDEX');c['decision_id']=decision_for('WA_MINEDEX',d)['decision_id']
        attrs=validate_candidate_pair(ROW,c,d,[c]);self.assertEqual(len(attrs),2)
        row={**ROW,'緯度':'-25'}
        with self.assertRaises(ValueError):validate_candidate_pair(row,c,d,[c])
    def test_resource_scope_never_invents_alias(self):
        c=normalize_feature('WA_MINEDEX',wa(),R);row={**ROW,'專案名稱':'Example — Yttria resource scope'}
        self.assertEqual(match_project(row,[c])['status'],'NO_EXACT_NAME_MATCH')
        result=match_project(row,[c],aliases=['Example'])
        self.assertEqual(result['status'],'AUTO_MATCHED_OFFICIAL_POINT');self.assertEqual(c['position_role'],ROLE)
    def test_transport_paging_snapshots_and_limits(self):
        calls=[]
        def f(url,**kw):
            calls.append((url,kw));return json.dumps({'features':[wa()], 'exceededTransferLimit':False}).encode(),{}
        with tempfile.TemporaryDirectory() as tmp:
            r=acquire_dataset('WA_MINEDEX',decision('WA_MINEDEX'),tmp,fetch=f)
            self.assertEqual(r['inventory']['count'],1);verify_acquisition_snapshots(r)
            self.assertIn('MONAZITE',calls[0][1]['params']['where']);self.assertEqual(calls[0][1]['max_attempts'],1)
            self.assertEqual(calls[0][1]['max_redirects'],0)
            r['features'][0]['feature']['attributes']['latitude']=-26
            with self.assertRaisesRegex(ValueError,'FEATURE_CACHE_NOT_COMPLETE_RAW_INVENTORY'):verify_acquisition_snapshots(r)
    def test_refusal_not_retried(self):
        f=Mock(side_effect=PermissionError('403'))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):acquire_dataset('WA_MINEDEX',decision('WA_MINEDEX'),tmp,fetch=f)
            self.assertEqual(f.call_count,1)
    def test_wfs_incomplete_count_refused(self):
        f=Mock(return_value=(json.dumps({'features':[],'numberMatched':1}).encode(),{}))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_PAGE'):acquire_dataset('GA_OZMIN',decision('GA_OZMIN'),tmp,fetch=f)
    def test_cli_null_bitwise_six_files(self):
        spec=importlib.util.spec_from_file_location('location_cli',ROOT/'tools/integrate_official_locations.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as tmp,patch('au_ree_v2.acquisition.request',side_effect=AssertionError('network')):
            result=m.run(ROOT/'results/asx-current',Path(tmp)/'out',acquisitions_path='nonexistent.json',acquire=True)
            self.assertTrue(result['baseline_bitwise_identical']);self.assertEqual(result['new_cells'],0)
            for name in m.BASE_FILES:self.assertEqual((ROOT/'results/asx-current'/name).read_bytes(),(Path(tmp)/'out/projection'/name).read_bytes())

if __name__=='__main__':unittest.main()


class OfficialLocationApprovedCliTests(unittest.TestCase):
    def test_approved_snapshot_pair_audits_and_preserves_old_values(self):
        spec=importlib.util.spec_from_file_location('location_cli_approved',ROOT/'tools/integrate_official_locations.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        _,rows=m.read_csv(ROOT/'results/asx-current/專案總表.csv')
        row=next(r for r in rows if not r['緯度'] and not r['經度'] and native_state(r['州省地區'])=='WA')
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);d=decision('WA_MINEDEX');(tmp/'decisions.json').write_text(json.dumps(d),encoding='utf8')
            f=Mock(return_value=(json.dumps({'features':[wa(row['專案名稱'])],'exceededTransferLimit':False}).encode(),{'Last-Modified':'Wed, 11 Nov 2026 00:00:00 GMT'}))
            acquired=acquire_dataset('WA_MINEDEX',d,tmp/'snapshots',fetch=f)
            (tmp/'acquired.json').write_text(json.dumps([acquired]),encoding='utf8')
            with patch('au_ree_v2.acquisition.request',side_effect=AssertionError('network')):
                result=m.run(ROOT/'results/asx-current',tmp/'out',tmp/'decisions.json',tmp/'acquired.json')
            self.assertEqual(result['new_cells'],2)
            audited=m.audit_summary(tmp/'out/projection');self.assertEqual(audited['filled_cells'],1987)
            _,after=m.read_csv(tmp/'out/projection/專案總表.csv')
            for old,new in zip(rows,after):
                for col,value in old.items():
                    if value:self.assertEqual(value,new[col])

class OfficialLocationAcquisitionTests(unittest.TestCase):
    def test_wfs_two_pages_exact_count(self):
        first={'properties':{'ENO':1}};second={'properties':{'ENO':2}}
        f=Mock(side_effect=[(json.dumps({'features':[first],'numberMatched':2}).encode(),{}),(json.dumps({'features':[second],'numberMatched':2}).encode(),{})])
        with tempfile.TemporaryDirectory() as tmp:
            r=acquire_dataset('GA_OZMIN',decision('GA_OZMIN'),tmp,fetch=f,page_size=1)
            self.assertEqual(r['inventory']['count'],2);self.assertEqual(f.call_count,2)
    def test_wfs_repeated_page_refused(self):
        f=Mock(return_value=(json.dumps({'features':[{'properties':{'ENO':1}}],'numberMatched':2}).encode(),{}))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'DUPLICATE'):acquire_dataset('GA_OZMIN',decision('GA_OZMIN'),tmp,fetch=f,page_size=1)
    def test_nt_zip_schema_only(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:z.writestr('occ.csv','Name,Longitude,Latitude\nExample,130,-20\n')
        f=Mock(return_value=(stream.getvalue(),{}))
        with tempfile.TemporaryDirectory() as tmp:
            r=acquire_dataset('NT_STRIKE',decision('NT_STRIKE'),tmp,fetch=f)
            self.assertEqual(r['features'],[]);self.assertEqual(r['field_report'][0]['columns'],['Name','Longitude','Latitude'])

class OfficialLocationRegistryTests(unittest.TestCase):
    def test_mixed_registry(self):
        d=decision('WA_MINEDEX')+[{'rule':'STAGE_MAPPING','scope':'all stages','decided_by':None},
             {'rule':'CE2O3_TO_CEO2_STOICHIOMETRIC','scope':'splinter-inferred500-r254-20151109','decided_by':None}]
        self.assertIsNotNone(decision_for('WA_MINEDEX',{'decisions':d}))
        self.assertIsNone(decision_for('GA_OZMIN',{'decisions':d}))
    def test_malformed_same_rule_scope(self):
        for scope in (None,'WA',[],1):
            with self.assertRaisesRegex(ValueError,'SCOPE_INVALID'):
                decision_for('WA_MINEDEX',[{'rule':RULE,'scope':scope}])

class OfficialLocationDistancePromotionTests(unittest.TestCase):
    def proof(self,tmp,lon=130,lat=-25,threshold=1000):
        p=Path(tmp)/'reference.txt';p.write_text('Reviewed reference coordinate fixture',encoding='utf8')
        return dict(source_path=str(p),source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),locator='fixture line 1',reviewed_by='fixture reviewer',longitude=lon,latitude=lat,crs='EPSG:7844',max_distance_m=threshold)
    def test_validator_rechecks_far_reference(self):
        d=decision('WA_MINEDEX');c=normalize_feature('WA_MINEDEX',wa(),R);c['decision_id']=decision_for('WA_MINEDEX',d)['decision_id']
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'DISTANT_FROM_VERIFIED_REFERENCE'):
                validate_candidate_pair(ROW,c,d,[c],verified_reference=self.proof(tmp))
    def test_validator_provenance_records_checked_or_absent(self):
        d=decision('WA_MINEDEX');c=normalize_feature('WA_MINEDEX',wa(),R);c['decision_id']=decision_for('WA_MINEDEX',d)['decision_id']
        attrs=validate_candidate_pair(ROW,c,d,[c])
        self.assertEqual(json.loads(attrs[0]['scope'])['distance_check'],'NO_VERIFIED_DISTANCE_COMPARATOR')
        with tempfile.TemporaryDirectory() as tmp:
            ref=self.proof(tmp,120,-25,10);attrs=validate_candidate_pair(ROW,c,d,[c],verified_reference=ref)
            scope=json.loads(attrs[0]['scope']);self.assertEqual(scope['distance_check'],'WITHIN_EXPLICIT_VERIFIED_THRESHOLD')
            self.assertEqual(scope['distance_m'],0);self.assertEqual(scope['distance_reference']['max_distance_m'],10)
    def test_reference_requires_source_hash_and_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref=self.proof(tmp);del ref['max_distance_m']
            with self.assertRaisesRegex(ValueError,'THRESHOLD'):validate_reference(ref)
            ref=self.proof(tmp);Path(ref['source_path']).write_text('changed')
            with self.assertRaisesRegex(ValueError,'SOURCE_HASH'):validate_reference(ref)
    def test_cli_far_reference_prevents_promotion(self):
        spec=importlib.util.spec_from_file_location('location_cli_distance',ROOT/'tools/integrate_official_locations.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        _,rows=m.read_csv(ROOT/'results/asx-current/專案總表.csv')
        row=next(r for r in rows if not r['緯度'] and not r['經度'] and native_state(r['州省地區'])=='WA')
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);d=decision('WA_MINEDEX');(tmp/'decisions.json').write_text(json.dumps(d),encoding='utf8')
            f=Mock(return_value=(json.dumps({'features':[wa(row['專案名稱'])],'exceededTransferLimit':False}).encode(),{}))
            a=acquire_dataset('WA_MINEDEX',d,tmp/'snapshots',fetch=f);(tmp/'acquired.json').write_text(json.dumps([a]),encoding='utf8')
            ref=self.proof(tmp);(tmp/'references.json').write_text(json.dumps({row['專案ID']:ref}),encoding='utf8')
            with patch('au_ree_v2.acquisition.request',side_effect=AssertionError('network')):
                result=m.run(ROOT/'results/asx-current',tmp/'out',tmp/'decisions.json',tmp/'acquired.json',references_path=tmp/'references.json')
            self.assertEqual(result['new_cells'],0);self.assertTrue(result['baseline_bitwise_identical'])
            _,queue=m.read_csv(tmp/'out/review_queue.csv');self.assertTrue(any(q['project_id']==row['專案ID'] and q['reason']=='DISTANT_FROM_VERIFIED_REFERENCE' for q in queue))
    def test_explicit_alias_context_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            proof=self.proof(tmp);proof['aliases']=['Example']
            p=Path(tmp)/'aliases.json';p.write_text(json.dumps({'test':proof}),encoding='utf8')
            refs,aliases=load_project_context(aliases_path=p)
            self.assertEqual(aliases['test']['aliases'],['Example']);self.assertEqual(refs,{})

class OfficialLocationCompleteInventoryTests(unittest.TestCase):
    def acquired(self,tmp):
        first=wa();second=wa();second['attributes']['site_code']=2
        f=Mock(side_effect=[(json.dumps({'features':[first],'exceededTransferLimit':True}).encode(),{}),(json.dumps({'features':[second],'exceededTransferLimit':False}).encode(),{})])
        return acquire_dataset('WA_MINEDEX',decision('WA_MINEDEX'),tmp,fetch=f,page_size=1)
    def test_omitted_competing_feature_from_real_two_feature_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=wa();second=wa();second['attributes']['site_code']=2
            f=Mock(return_value=(json.dumps({'features':[first,second],'exceededTransferLimit':False}).encode(),{}))
            r=acquire_dataset('WA_MINEDEX',decision('WA_MINEDEX'),tmp,fetch=f)
            r['features']=r['features'][:1];r['inventory']['count']=1
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_COUNT|CACHE_NOT_COMPLETE'):verify_acquisition_snapshots(r)
    def test_omitted_terminal_page_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.acquired(tmp);r['receipts']=r['receipts'][:1];r['features']=r['features'][:1];r['inventory']['count']=1;r['network_requests']=1
            with self.assertRaisesRegex(ValueError,'TERMINAL_PAGE_MISSING'):verify_acquisition_snapshots(r)
    def test_omitted_first_page_rejected_even_count_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.acquired(tmp);r['receipts']=r['receipts'][1:];r['features']=r['features'][1:];r['inventory']['count']=1;r['network_requests']=1
            with self.assertRaisesRegex(ValueError,'QUERY_PAGINATION'):verify_acquisition_snapshots(r)
    def test_mutated_filter_offset_receipt_and_count_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=self.acquired(tmp)
            for mode in ('count','filter','offset','decision','dataset','layer'):
                r=copy.deepcopy(original)
                if mode=='count':r['inventory']['count']=1
                elif mode=='filter':r['inventory']['filter']='1=1'
                elif mode=='offset':r['receipts'][1]['url']=r['receipts'][1]['url'].replace('resultOffset=1','resultOffset=0')
                else:r['receipts'][0][mode if mode!='decision' else 'decision_id']='tampered'
                with self.subTest(mode=mode),self.assertRaises(ValueError):verify_acquisition_snapshots(r)
    def test_changed_wfs_total_rejected_against_raw_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Mock(return_value=(json.dumps({'features':[{'properties':{'ENO':1}}],'numberMatched':1}).encode(),{}))
            r=acquire_dataset('GA_OZMIN',decision('GA_OZMIN'),tmp,fetch=f);r['inventory']['count']=2
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_COUNT'):verify_acquisition_snapshots(r)
    def test_build_candidates_also_validates_complete_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=self.acquired(tmp);r['features']=r['features'][:1];r['inventory']['count']=1
            with self.assertRaises(ValueError):build_location_candidates([r],decision('WA_MINEDEX'))
