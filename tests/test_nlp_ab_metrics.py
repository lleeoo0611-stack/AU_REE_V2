import unittest

from tools.score_nlp_page_retrieval import score


class RetrievalMetricsTest(unittest.TestCase):
    def test_unknown_and_quarantine_are_not_failures_or_negatives(self):
        def ref(col, status, pages):
            return {'project_id':'P','column':col,'judgment':status,
                    'pages':[{'sha256':s,'page':p} for s,p in pages]}
        docs={'documents':[{'sha256':'A','pages':3,'split':'holdout'},{'sha256':'B','pages':2,'split':'quarantine'}]}
        def query(group, cols, left, right):
            return {'case_id':group,'project_id':'P','field':group,'columns':cols,'rules':left,'rules_nlp':right}
        pred={'k':5,'cases':[query('coordinate',['lat','lon'],[],[['A',2]]),
                              query('deposit',['code'],[],[]),query('stage',['stage'],[],[])]}
        refs=[ref('lat','CONTEXT_ONLY',[('A',2)]),ref('lon','CONTEXT_ONLY',[('A',2)]),
              ref('code','CONTEXT_ONLY',[('B',1)]),ref('stage','UNJUDGED',[])]
        result,qs,cs=score(pred,docs,refs)
        self.assertEqual(result['query']['rules_nlp']['hit5'],{'hits':1,'n':1,'rate':1.0})
        self.assertEqual(result['cell']['rules_nlp']['hit5']['hits'],2)
        self.assertEqual(result['query']['references_outside_pool'],1)
        self.assertEqual(result['query']['unjudged'],1)
        self.assertIsNone(result['query']['rules_nlp']['sufficient_hit5']['rate'])
        self.assertEqual(result['query']['rules_nlp']['page_slots'],1)
        pred['cases'][0]['rules_nlp']=[['B',1]]
        with self.assertRaises(ValueError):
            score(pred,docs,refs)
