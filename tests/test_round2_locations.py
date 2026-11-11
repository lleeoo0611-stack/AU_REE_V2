import unittest
from au_ree_v2.round2_locations import normalized_name,operator_name,match_project,transform_nt,decision_for,NAME_RULE,SCOPES,APPROVAL_EVIDENCE

class Round2LocationTests(unittest.TestCase):
    def row(self,name='Rankin Dome Rare Earth Project',operator='ACM Limited',pid='one'):
        return {'專案ID':pid,'專案名稱':name,'州省地區':'WA','開發商':operator,'緯度':'','經度':''}
    def candidate(self,name='Rankin Dome REE',operator='',group='one',fid='one'):
        return dict(dataset='GA_OZMIN',state='WA',names=[name],normalized_names=[normalized_name(name)],operator=operator,project_group=group,feature_id=fid)
    def test_normalization(self):
        self.assertEqual(normalized_name('Rankin Dome Rare Earth Project'),normalized_name('Rankin Dome REE'))
        self.assertEqual(normalized_name('Rankin Dome Rare-Earth Project'),normalized_name('Rankin Dome REE'))
        self.assertEqual(normalized_name('Cascade Rare Earth Project — Meeka'),'cascade')
        self.assertEqual(normalized_name('FOO historical deposit, prospect exploration resource scope'),'foo')
    def test_unique(self):
        self.assertEqual(match_project(self.row(),[self.candidate()])['status'],'AUTO_MATCHED_NORMALIZED_NAME')
    def test_company_reject(self):
        c=self.candidate('Cascade','Zinc of Ireland');r=self.row('Cascade Rare Earth Project — Meeka','Meeka Gold Limited')
        self.assertEqual(match_project(r,[c])['status'],'OPERATOR_MISMATCH')
        r['開發商']='Zinc of Ireland NL'
        self.assertEqual(match_project(r,[c])['status'],'AUTO_MATCHED_NORMALIZED_NAME')
    def test_multi_site(self):
        a=self.candidate();b=self.candidate('Other site',fid='two')
        self.assertEqual(match_project(self.row(),[a,b])['status'],'MULTIPLE_CANDIDATES')
    def test_shared_point(self):
        r=self.row();other=self.row(pid='two')
        self.assertEqual(match_project(r,[self.candidate()],[r,other])['status'],'POINT_MATCHES_MULTIPLE_RESEARCH_ROWS')
    def test_existing_partial_pair(self):
        r=self.row();r['緯度']='-20'
        self.assertEqual(match_project(r,[self.candidate()])['status'],'EXISTING_PAIR_UNCHANGED')
    def test_state(self):
        r=self.row();r['州省地區']='NT'
        self.assertEqual(match_project(r,[self.candidate()])['status'],'NO_NORMALIZED_NAME_MATCH')
    def test_uro(self):
        r=self.row('Charley Creek North Project — historical URO EL33004 exploration','URO Corporation Pty Ltd');r['州省地區']='NT'
        self.assertEqual(match_project(r,[])['status'],'TENEMENT_SCOPE_REQUIRES_RESEARCHER_DECISION')
    def test_nt_requires_datum(self):
        with self.assertRaisesRegex(ValueError,'METADATA'):transform_nt(500000,8000000,53,None)
    def test_nt_projection_reference(self):
        # Analytic central-meridian point: zone 53 easting 500000 at equator
        # southward northing derived from published EPSG transverse Mercator.
        lon,lat=transform_nt(500000,7788518.692,53,'GDA94')
        self.assertAlmostEqual(lon,135,places=4)
        self.assertAlmostEqual(lat,-20,places=4)
    def test_wa_missing_operator_rejected(self):
        c=self.candidate();c['dataset']='WA_MINEDEX'
        self.assertEqual(match_project(self.row(),[c])['status'],'OPERATOR_FIELD_VALUE_MISSING')
    def test_decision_scope_date_evidence(self):
        d=dict(rule=NAME_RULE,decision_id='test',decided_by='USER_EXPLICIT_APPROVAL',scope=SCOPES[NAME_RULE],decided_date='2026-11-11',approval_evidence=APPROVAL_EVIDENCE)
        self.assertEqual(decision_for(NAME_RULE,[d]),d)
        for key,value in [('scope','OTHER'),('decided_date','2026-11-10'),('approval_evidence','unrelated')]:
            with self.subTest(key=key): self.assertIsNone(decision_for(NAME_RULE,[dict(d,**{key:value})]))
    def test_approval_gate(self):
        self.assertIsNone(decision_for(NAME_RULE,{'decisions':[]}))

if __name__=='__main__':unittest.main()
