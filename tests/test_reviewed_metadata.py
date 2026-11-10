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
