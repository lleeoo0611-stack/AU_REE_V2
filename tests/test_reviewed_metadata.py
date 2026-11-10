import copy,unittest
import pymupdf
from au_ree_v2.source_cells import norm
from au_ree_v2.reviewed_metadata import validate_listing_proof

class ListingProof(unittest.TestCase):
    def make(self, exchange='ASX', statement='Example retains 100% ownership of the Mock Project.'):
        doc=pymupdf.open();p=doc.new_page();p.insert_text((50,50),f'Example Resources Limited ({exchange}: EXM)',fontsize=10)
        p=doc.new_page();p.insert_text((50,50),statement,fontsize=10)
        b=p.search_for(statement)[0]
        proof=dict(issuer='Example Resources Limited',issuer_alias='Example',project_marker='Mock Project',exchange=exchange,ticker='EXM',
            listing_evidence=dict(page=1,markers=['Example Resources Limited']),ownership_evidence=dict(page=2,markers=['Mock Project']),
            ownership_statement=statement,ownership_bbox=[b.x0-.2,b.y0-.2,b.x1+.2,b.y1+.2])
        def evidence(e):
            text=norm(doc[e['page']-1].get_text(sort=True))
            if any(norm(m) not in text for m in e['markers']):raise ValueError('MARKER_MISMATCH')
            return text
        self.addCleanup(doc.close)
        return doc,proof,evidence
    def test_asx_current_ownership(self):
        self.assertIn('SOURCE_BOUND',validate_listing_proof(*self.make()))
    def test_lse_cross_page_subsidiary_ownership(self):
        args=self.make('LSE','The Mock Project is owned 100% by Subsidiary, wholly owned by Example Resources Limited.')
        self.assertIn('SOURCE_BOUND',validate_listing_proof(*args))
    def test_wrong_ticker(self):
        d,p,e=self.make();p['ticker']='WRONG'
        with self.assertRaisesRegex(ValueError,'TICKER_NOT_BOUND'):validate_listing_proof(d,p,e)
    def test_wrong_issuer(self):
        d,p,e=self.make();p.update(issuer='Other Limited',issuer_alias='Other')
        with self.assertRaisesRegex(ValueError,'TICKER_NOT_BOUND'):validate_listing_proof(d,p,e)
    def test_unrelated_project(self):
        d,p,e=self.make();p['project_marker']='Different Project'
        with self.assertRaisesRegex(ValueError,'ISSUER_PROJECT_MISMATCH'):validate_listing_proof(d,p,e)
    def test_partial_ownership(self):
        with self.assertRaisesRegex(ValueError,'FULL_OWNERSHIP'):validate_listing_proof(*self.make(statement='Example retains 50% ownership of the Mock Project.'))
    def test_owns_full_interest_of_named_project(self):
        self.assertIn('SOURCE_BOUND',validate_listing_proof(*self.make(statement='Example owns 100% of the Mock Project.')))
        for text in ['Example owns 80% of the Mock Project.',
                     'Example no longer owns 100% of the Mock Project.']:
            with self.subTest(text=text),self.assertRaises(ValueError):
                validate_listing_proof(*self.make(statement=text))
        doc,proof,evidence=self.make(statement='Example owns 100% of the Mock Project.')
        proof['project_marker']='Unrelated Project'
        with self.assertRaisesRegex(ValueError,'ISSUER_PROJECT_MISMATCH'):
            validate_listing_proof(doc,proof,evidence)
    def test_spelled_percentage_keeps_full_ownership_requirement(self):
        self.assertIn('SOURCE_BOUND',validate_listing_proof(*self.make(statement='Example operates the 100 per cent-owned Mock Project.')))
        for text in ['Example operates the 50 per cent-owned Mock Project.',
                     'Example no longer operates the 100 per cent-owned Mock Project.']:
            with self.subTest(text=text),self.assertRaises(ValueError):
                validate_listing_proof(*self.make(statement=text))
    def test_negated_ownership(self):
        with self.assertRaisesRegex(ValueError,'NOT_AFFIRMED'):validate_listing_proof(*self.make(statement='Example does not retain 100% ownership of the Mock Project.'))
    def test_completed_full_acquisition_is_not_an_option_or_future_acquisition(self):
        self.assertIn('SOURCE_BOUND',validate_listing_proof(*self.make(statement='Example acquired 100% of the Mock Project.')))
        for text in ['Example will acquire 100% of the Mock Project.',
                     'Example will have acquired 100% of the Mock Project.',
                     'Example may have acquired 100% of the Mock Project.',
                     'Example has an option to acquire 100% of the Mock Project.',
                     'Example acquired 80% of the Mock Project.',
                     'Example has not acquired 100% of the Mock Project.']:
            with self.subTest(text=text),self.assertRaises(ValueError):validate_listing_proof(*self.make(statement=text))
    def test_mutated_statement(self):
        d,p,e=self.make();p['ownership_statement']='Example owns the Mock Project.'
        with self.assertRaisesRegex(ValueError,'STATEMENT_MISMATCH'):validate_listing_proof(d,p,e)
    def test_named_project_full_holding_requires_affirmed_present_interest(self):
        for text in ['Example holds 100% of the Mock Project.', 'Example hold a 100% of the Mock Project.']:
            with self.subTest(text=text):self.assertIn('SOURCE_BOUND',validate_listing_proof(*self.make(statement=text)))
        for text in ['Example will hold 100% of the Mock Project.',
                     'Example may hold a 100% of the Mock Project.',
                     'Example has an option to hold 100% of the Mock Project.',
                     'Example does not hold 100% of the Mock Project.',
                     'Example holds 80% of the Mock Project.']:
            with self.subTest(text=text),self.assertRaises(ValueError):validate_listing_proof(*self.make(statement=text))
    def test_invalid_exchange(self):
        d,p,e=self.make();p['exchange']='UNVERIFIED'
        with self.assertRaisesRegex(ValueError,'EXCHANGE_OR_TICKER'):validate_listing_proof(d,p,e)
    def test_outside_page_region(self):
        d,p,e=self.make();p['ownership_bbox']=[-1,0,100,100]
        with self.assertRaisesRegex(ValueError,'REGION_INVALID'):validate_listing_proof(d,p,e)

    def test_reviewed_percentage_heading_requires_exact_project_region(self):
        for label in ['Mock Project (100%)', 'Mock Project (50%)',
                      'Different Project (100%)', 'Mock Project (100% recovery)',
                      'Option for Mock Project (100%)', 'Mock Project (100%) target']:
            with self.subTest(label=label):
                d,p,e=self.make(statement='Example Resources Limited. '+label)
                b=d[1].search_for(label)[0]
                p['project_interest_heading']=dict(page=2,markers=[label],bbox=list(b))
                if label=='Mock Project (100%)':
                    self.assertIn('SOURCE_BOUND',validate_listing_proof(d,p,e))
                    bad=copy.deepcopy(p);bad['project_interest_heading']['page']=1
                    with self.assertRaises(ValueError):validate_listing_proof(d,bad,e)
                    bad=copy.deepcopy(p);bad.pop('project_interest_heading')
                    with self.assertRaises(ValueError):validate_listing_proof(d,bad,e)
                else:
                    with self.assertRaises(ValueError):validate_listing_proof(d,p,e)

    def test_full_words_bind_exact_issuer_and_reject_future_or_partial(self):
        for text in ['The Mock Project is fully owned by Example Resources Limited.',
                     'The Mock Project is wholly owned by Example Resources Limited.',
                     'The Mock Project is partially owned by Example Resources Limited.',
                     'The Mock Project will be fully owned by Example Resources Limited.',
                     'The Mock Project may be wholly owned by Example Resources Limited.',
                     'The Mock Project is not fully owned by Example Resources Limited.',
                     'Example holds the Mock Project, fully owned by Different Limited.']:
            with self.subTest(text=text):
                if text.startswith('The Mock Project is fully') or text.startswith('The Mock Project is wholly'):
                    self.assertIn('SOURCE_BOUND',validate_listing_proof(*self.make(statement=text)))
                else:
                    with self.assertRaises(ValueError):validate_listing_proof(*self.make(statement=text))

    def test_dated_developer_listing_does_not_claim_full_project_ownership(self):
        from au_ree_v2.reviewed_metadata import validate_issuer_code_association,issuer_label
        d,p,e=self.make(statement='The Mock Project is an exploration project.')
        a=dict(column='未上市公司',value='否',evidence=dict(page=2,markers=['Mock Project']),issuer_code_association=dict(exchange='ASX',ticker='EXM',issuer='Example Resources Limited',project_marker='Mock Project',listing_evidence=p['listing_evidence'],project_evidence=dict(page=2,markers=['Mock Project']),interpretation='DATED_DEVELOPER_LISTING_NOT_PROJECT_OWNERSHIP'))
        r=dict(effective_date_role='DATED_ISSUER_METADATA',observations=[],identity_evidence=dict(page=2,markers=['Mock Project']))
        self.assertIn('NOT_OWNERSHIP',validate_issuer_code_association(d,a,['Mock Project'],e,r))
        for change in [dict(ticker='OTHER'),dict(issuer='Different Limited'),dict(project_marker='Unrelated'),dict(project_marker='Mock'),dict(interpretation='CURRENT_FULL_OWNERSHIP')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                bad=copy.deepcopy(a);bad['issuer_code_association'].update(change);validate_issuer_code_association(d,bad,['Mock Project'],e,r)
        for change in [dict(value='是'),dict(column='TREO品位_pct')]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_issuer_code_association(d,dict(a,**change),['Mock Project'],e,r)
        for change in [dict(study={'scale':'DFS_MODEL'}),dict(observations=[{'value':1}]),dict(effective_date_role='RESOURCE_EFFECTIVE_DATE')]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_issuer_code_association(d,a,['Mock Project'],e,dict(r,**change))
        self.assertEqual(issuer_label('Example Resources Ltd'),issuer_label('Example Resources Limited'))
        self.assertNotEqual(issuer_label('Example Resources Pty Ltd'),issuer_label('Example Resources Limited'))
        self.assertNotEqual(issuer_label('Renamed Gold Ltd'),issuer_label('Example Resources Limited'))

    def test_explicit_listing_code_phrases_reject_wrong_code_and_delisting(self):
        from au_ree_v2.reviewed_metadata import validate_issuer_code_association
        texts=['The company is listed as Example Resources Limited with an ASX code of EXM.',
               'Example Resources Limited listed on Australian Securities Exchange (ASX) under the code EXM',
               'ASX code Example Resources Limited is listed on the Australian Securities Exchange (Shares: EXM)']
        for text in texts:
            with self.subTest(text=text):
                d,p,e=self.make(statement='Mock Project exploration')
                d[0].add_redact_annot(d[0].rect);d[0].apply_redactions();d[0].insert_textbox((40,40,550,200),text,fontsize=10)
                a=dict(column='未上市公司',value='否',issuer_code_association=dict(exchange='ASX',ticker='EXM',issuer='Example Resources Limited',project_marker='Mock Project',listing_evidence=dict(page=1,markers=['Example Resources Limited']),project_evidence=dict(page=2,markers=['Mock Project']),interpretation='DATED_DEVELOPER_LISTING_NOT_PROJECT_OWNERSHIP'))
                r=dict(effective_date_role='DATED_ISSUER_METADATA',observations=[],identity_evidence=dict(page=2,markers=['Mock Project']))
                self.assertIn('NOT_OWNERSHIP',validate_issuer_code_association(d,a,['Mock Project'],e,r))
                bad=copy.deepcopy(a);bad['issuer_code_association']['ticker']='WRG'
                with self.assertRaises(ValueError):validate_issuer_code_association(d,bad,['Mock Project'],e,r)
                d[0].insert_text((40,230),'The company is no longer listed.')
                with self.assertRaises(ValueError):validate_issuer_code_association(d,a,['Mock Project'],e,r)

    def test_listing_association_short_project_phrase_is_opt_in_and_metadata_only(self):
        from au_ree_v2.reviewed_metadata import validate_issuer_code_association
        d,p,e=self.make(statement='Duke Rare Earth Project exploration')
        a=dict(column='未上市公司',value='否',issuer_code_association=dict(exchange='ASX',ticker='EXM',issuer='Example Resources Limited',project_marker='Duke',registered_short_project_phrase=True,listing_evidence=p['listing_evidence'],project_evidence=dict(page=2,markers=['Duke Rare Earth Project']),interpretation='DATED_DEVELOPER_LISTING_NOT_PROJECT_OWNERSHIP'))
        r=dict(effective_date_role='DATED_ISSUER_METADATA',observations=[],identity_evidence=dict(page=2,markers=['Duke Rare Earth Project']))
        self.assertIn('NOT_OWNERSHIP',validate_issuer_code_association(d,a,['Duke'],e,r))
        for change in [dict(registered_short_project_phrase=False),dict(project_marker='Mock'),dict(project_marker='Duke Other')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                bad=copy.deepcopy(a);bad['issuer_code_association'].update(change);validate_issuer_code_association(d,bad,['Duke'],e,r)
        with self.assertRaises(ValueError):validate_issuer_code_association(d,a,['Different Project'],e,r)
        with self.assertRaises(ValueError):validate_issuer_code_association(d,a,['Duke'],e,dict(r,identity_evidence=dict(page=1)))

    def test_company_listing_is_shared_only_as_a_guarded_company_property(self):
        from au_ree_v2.reviewed_metadata import validate_issuer_code_association
        d,p,e=self.make(statement='The Other Project is an exploration project.')
        a=dict(column='未上市公司',value='否',issuer_code_association=dict(exchange='ASX',ticker='EXM',issuer='Example Resources Limited',listing_evidence=p['listing_evidence'],company_level_only=True,interpretation='DATED_DEVELOPER_LISTING_NOT_PROJECT_OWNERSHIP'))
        r=dict(effective_date_role='DATED_ISSUER_METADATA',observations=[],attributes=[a])
        self.assertIn('COMPANY_PROPERTY_ONLY',validate_issuer_code_association(d,a,['Target Project'],e,r))
        with self.assertRaises(ValueError):validate_issuer_code_association(d,a,['Target Project'],e,dict(r,observations=[{'value':1}]))
        with self.assertRaises(ValueError):validate_issuer_code_association(d,a,['Target Project'],e,dict(r,attributes=[a,dict(column='開發商',value='Other')]))
        # A separate explicit listing affirmation must name this legal issuer.
        d[0].add_redact_annot(d[0].rect);d[0].apply_redactions();d[0].insert_text((40,40),'Listed on Australian Securities Exchange (ASX) ASX Code: EXM')
        d[1].insert_text((40,100),'Example Resources Limited is a listed public company.')
        a['issuer_code_association']['listing_evidence']=dict(page=1,markers=['ASX Code: EXM'])
        a['issuer_code_association']['issuer_listing_affirmation_evidence']=dict(page=2,markers=['Example Resources Limited is a listed public company'])
        self.assertIn('COMPANY_PROPERTY_ONLY',validate_issuer_code_association(d,a,[],e,r))
        bad=copy.deepcopy(a);bad['issuer_code_association']['issuer']='Different Limited'
        with self.assertRaises(ValueError):validate_issuer_code_association(d,bad,[],e,r)

    def test_official_release_url_is_literal_listing_metadata_only(self):
        from au_ree_v2.reviewed_metadata import validate_issuer_release_url
        r=dict(url='https://announcements.asx.com.au/asxpdf/20240328/pdf/abc123.pdf',publication_date='2024-03-28',publication_date_role='ASX_DATED_URL_NATIVE_ISSUER',effective_date_role='DATED_ISSUER_METADATA',date_precision='DAY',observations=[],attributes=[dict(column='未上市公司',value='否',issuer_code_association={'issuer':'Example Limited'})])
        validate_issuer_release_url(r,'2026-11-05')
        for change in [dict(url=r['url']+'?date=20240328'),dict(url=r['url']+'#anchor'),dict(url=r['url'].replace('announcements.asx.com.au','announcements.asx.com.au.evil.test')),dict(url=r['url'].replace('https://','https://user@')),dict(publication_date='2024-03-27'),dict(date_precision='MONTH'),dict(effective_date_role='RESOURCE_EFFECTIVE_DATE'),dict(observations=[{'value':1}]),dict(study={'scale':'DFS_MODEL'}),dict(attributes=[dict(column='TREO品位_pct',value=1,issuer_code_association={'issuer':'Example Limited'})])]:
            with self.subTest(change=change),self.assertRaises(ValueError):validate_issuer_release_url(dict(r,**change),'2026-11-05')
