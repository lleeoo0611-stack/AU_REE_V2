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
    def test_negated_ownership(self):
        with self.assertRaisesRegex(ValueError,'NOT_AFFIRMED'):validate_listing_proof(*self.make(statement='Example does not retain 100% ownership of the Mock Project.'))
    def test_mutated_statement(self):
        d,p,e=self.make();p['ownership_statement']='Example owns the Mock Project.'
        with self.assertRaisesRegex(ValueError,'STATEMENT_MISMATCH'):validate_listing_proof(d,p,e)
    def test_invalid_exchange(self):
        d,p,e=self.make();p['exchange']='UNVERIFIED'
        with self.assertRaisesRegex(ValueError,'EXCHANGE_OR_TICKER'):validate_listing_proof(d,p,e)
    def test_outside_page_region(self):
        d,p,e=self.make();p['ownership_bbox']=[-1,0,100,100]
        with self.assertRaisesRegex(ValueError,'REGION_INVALID'):validate_listing_proof(d,p,e)
