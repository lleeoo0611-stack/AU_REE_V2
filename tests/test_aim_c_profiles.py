"""Source availability, distinct projects, incomplete matrices and filtered cases."""
import tempfile
import unittest
from pathlib import Path

from au_ree_v2.census_release import aim_c_profiles
from au_ree_v2.tabular import read_csv


class AimCProfileTests(unittest.TestCase):
    def test_canonical_alias_and_scoped_estimates_are_not_independent_ranked_cases(self):
        rows = [{'專案ID':k} for k in ('canonical','alias','other','no-id','unranked')]
        selected = [dict(project_id=p, canonical_project_id=q, status=status)
                    for p,q,status in (('canonical','canonical','FILTER_EXCLUDED'),('alias','canonical','SELECTED'),
                              ('other','other','SELECTED'),('no-id','','UNRESOLVED_PROJECT'),('unranked','unranked','SELECTED'))]
        scopes = [dict(project_id='alias', statement_group_id='one', scope='Deposit only', selected_for_census=1)]*2
        citations = [dict(project_id='alias', value='observed', source_sha256='one;two'),
                     dict(project_id='alias', value='more', source_sha256='one'),
                     dict(project_id='alias', value='', source_sha256='pending')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            counts = aim_c_profiles(path, rows, citations, [dict(sha256='one',kind='pdf')], scopes, selected,
                                    [dict(project_id='alias'),dict(project_id='unranked')], [dict(project_id='alias')]*3)
            profiles = {r['project_id']: r for r in read_csv(path/'aim_c_availability.csv')}
        self.assertEqual(counts['unique_canonical_projects'], {'SIX_DOMAIN_RANKED':1,
            'SIX_DOMAIN_MATRIX_UNRANKED':1,'SELECTED_WITHOUT_SIX_DOMAIN_INPUT':1})
        self.assertEqual(profiles['canonical']['six_domain_group'],'FILTER_EXCLUDED')
        self.assertEqual(profiles['no-id']['six_domain_group'],'UNRESOLVED_PROJECT')
        self.assertEqual(profiles['alias']['selected_statement_groups'],'1')
        self.assertEqual(profiles['alias']['source_versions_in_populated_fields'],'2')
        self.assertEqual(profiles['alias']['pdf_versions_in_populated_fields'],'1')
        self.assertEqual(profiles['unranked']['ore_mt'],'')
