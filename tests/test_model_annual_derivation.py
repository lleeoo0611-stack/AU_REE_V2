"""Narrow cross-table Base Case derivation: source-bound and labeled modeled."""
import copy,unittest
import pymupdf
from au_ree_v2.model_annual_derivation import validate_model_annual_derivation,METHOD,PROFILE
from au_ree_v2.source_cells import region_text

class ModelAnnualNdPrTests(unittest.TestCase):
 def setUp(self):
  self.doc=pymupdf.open();self.addCleanup(self.doc.close)
  for _ in range(2):self.doc.new_page()
  p=self.doc[0]
  for x,y,t in [(20,30,'Table 4.2 | Processing and Production Assumptions'),(350,50,'Base Case'),(20,90,'Average annual contained TREO in MREC'),(300,90,'tpa'),(350,90,'8,300')]:p.insert_text((x,y),t,fontsize=10)
  b=dict(field='average_annual_treo_product_t',scope='scope',page=1,mode='native_cell',original_unit='tpa',table_bbox=[10,15,480,100],table_label_bbox=[19,18,300,32],table_label='Table 4.2 | Processing and Production Assumptions',row_bbox=[10,77,480,94],row_label_bbox=[19,77,280,94],row_label='Average annual contained TREO in MREC',column_bbox=[340,35,410,100],column_label_bbox=[349,37,401,52],column_label='Base Case',unit_bbox=[299,77,320,94])
  self.review=dict(source_sha256='a'*64,statement_id='s',scope='scope',effective_date='2026-10-20')
  self.study=dict(scale='SCOPING_MODEL',endpoint='MREC',selected_scenario='Base Case',parameters={'average_annual_treo_product_t':8300},parameter_bindings={'average_annual_treo_product_t':b},annual_basis_evidence={'page':1})
  contract=self.review.copy()
  self.spec=dict(method=METHOD,profile=PROFILE,assurance='MODEL_ASSUMPTION_DERIVED_NOT_DIRECT_REPORTED_OUTPUT',**contract,inputs=[],rounding_interval_tpa=[2043.525,2069.965])
  def proof(page,bbox,text):
   self.doc[page-1].insert_textbox(pymupdf.Rect(bbox),text,fontsize=9)
   return dict(page=page,bbox=bbox,text=region_text(self.doc[page-1],pymupdf.Rect(bbox)),evidence={'page':page,'markers':['model']})
  self.spec['annual_model_proof']=proof(1,[20,150,570,230],'The Base Case reflects the metallurgical recovery and production assumptions adopted in the Scoping Study financial model. Base Case annual production represents the life-of-mine annual average and includes ramp-up and scheduling effects.')
  self.spec['composition_origin_proof']=proof(2,[20,30,570,80],'The Base Case MREC composition is based on the high-grade MREC produced by a laboratory.')
  self.spec['composition_model_proof']=proof(2,[20,100,570,170],'The distribution of the four principal magnet rare earth oxides and yttrium in the Base Case MREC is presented in Table 5.3.')
  p=self.doc[1]
  # ASCII digits and Unicode subscripts represent the same exact oxide.
  for x,y,t in [(20,210,'Table 5.3 | Key Rare Earth Distribution in MREC'),(350,230,'% of contained TREO'),(20,260,'Neodymium (Nd2O3)'),(350,260,'19.27'),(20,290,'Praseodymium (Pr6O11)'),(350,290,'5.51')]:p.insert_text((x,y),t,fontsize=10)
  self.spec['inputs'].append(dict(name='annual_treo_t',value=8300,original_token='8,300',unit='tpa',rounding_half_width=50,evidence={'page':1},cell_binding=copy.deepcopy(b),**contract))
  for name,basis,v,token,y in [('nd_percent_of_treo','Nd2O3',19.27,'19.27',260),('pr_percent_of_treo','Pr6O11',5.51,'5.51',290)]:
   b=dict(mode='native_cell',scope='scope',page=2,table_bbox=[10,195,480,300],table_label_bbox=[19,198,300,213],row_bbox=[10,y-12,480,y+3],column_bbox=[340,215,460,300],column_label_bbox=[349,218,450,233],row_label_bbox=[19,y-12,180,y+3])
   self.spec['inputs'].append(dict(name=name,basis=basis,value=v,original_token=token,unit='%TREO',rounding_half_width=.005,evidence={'page':2},cell_binding=b,**contract))
 def run_spec(self,s=None,r=None,study=None,value=2056.74):return validate_model_annual_derivation(self.doc,r or self.review,study or self.study,s or self.spec,value,lambda e:'verified')
 def test_native_round_trip_and_interval(self):self.assertAlmostEqual(self.run_spec(),2056.74)
 def test_wrong_model_and_product_rejected(self):
  for key,value in [('selected_scenario','Design'),('endpoint','REEC'),('scale','DFS_MODEL')]:
   s=copy.deepcopy(self.study);s[key]=value
   with self.assertRaisesRegex(ValueError,'PROFILE'):self.run_spec(study=s)
 def test_scope_date_source_mismatch(self):
  for key in ('scope','source_sha256','statement_id','effective_date'):
   s=copy.deepcopy(self.spec);s[key]='wrong'
   with self.assertRaisesRegex(ValueError,'MISMATCH'):self.run_spec(s)
 def test_input_cross_source_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'][1]['source_sha256']='b'*64
  with self.assertRaisesRegex(ValueError,'INPUT_SOURCE'):self.run_spec(s)
 def test_missing_pr_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'].pop()
  with self.assertRaisesRegex(ValueError,'THREE_INPUTS'):self.run_spec(s)
 def test_resource_share_cannot_replace_product(self):
  s=copy.deepcopy(self.spec);s['composition_model_proof']['text']='Mineral Resource oxide composition'
  with self.assertRaisesRegex(ValueError,'PROOF_TEXT'):self.run_spec(s)
 def test_wrong_denominator_column_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'][1]['cell_binding']['column_label_bbox']=[19,248,180,263]
  with self.assertRaisesRegex(ValueError,'ANCHOR'):self.run_spec(s)
 def test_borrowed_numeric_token_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'][1]['value']=11.15;s['inputs'][1]['original_token']='11.15'
  with self.assertRaisesRegex(ValueError,'TOKEN'):self.run_spec(s)
 def test_other_share_species_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'][2]['basis']='Dy2O3'
  with self.assertRaisesRegex(ValueError,'BASIS'):self.run_spec(s)
 def test_wrong_annual_9300_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'][0]['value']=9300;s['inputs'][0]['original_token']='9,300'
  with self.assertRaisesRegex(ValueError,'SELECTED_ANNUAL'):self.run_spec(s)
 def test_input_rounding_cannot_be_zero(self):
  s=copy.deepcopy(self.spec);s['inputs'][1]['rounding_half_width']=0
  with self.assertRaisesRegex(ValueError,'ROUNDING'):self.run_spec(s)
 def test_output_interval_cannot_be_zero(self):
  s=copy.deepcopy(self.spec);s['rounding_interval_tpa']=[2056.74,2056.74]
  with self.assertRaisesRegex(ValueError,'ROUNDING'):self.run_spec(s)
 def test_output_is_computed(self):
  with self.assertRaisesRegex(ValueError,'RESULT_MISMATCH'):self.run_spec(value=2057)
 def test_assurance_cannot_be_direct_reported(self):
  s=copy.deepcopy(self.spec);s['assurance']='REPORTED'
  with self.assertRaisesRegex(ValueError,'PROFILE'):self.run_spec(s)
 def test_wrong_page_rejected(self):
  s=copy.deepcopy(self.spec);s['inputs'][1]['cell_binding']['page']=1
  with self.assertRaisesRegex(ValueError,'BINDING'):self.run_spec(s)

if __name__=='__main__':unittest.main()
