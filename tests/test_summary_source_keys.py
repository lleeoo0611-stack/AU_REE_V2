import copy,unittest
from au_ree_v2.project_summary import merge_summary_sources


class IdentitySourceKeys(unittest.TestCase):
    def test_cross_ledger_key_collision_fails_before_mutating_sources(self):
        selected={'sha':dict(key='annual',url='https://issuer.test/annual.pdf')}
        old=copy.deepcopy(selected)
        with self.assertRaisesRegex(ValueError,'IDENTITY_SOURCE_KEY_REPLACEMENT'):
            merge_summary_sources(selected,{'new':dict(key='new'),'sha':dict(key='metadata')},[dict(identity_source='annual')])
        self.assertEqual(old,selected)

    def test_shared_project_identity_key_preserves_source_and_accepts_verified_url_update(self):
        selected={'sha':dict(key='annual',url='https://issuer.test/annual.pdf')}
        incoming={'sha':dict(key='annual',url='https://asx.test/annual.pdf')}
        merge_summary_sources(selected,incoming,[dict(identity_source='annual'),dict(identity_source='annual')])
        self.assertEqual(incoming,selected)

    def test_non_identity_technical_source_does_not_create_new_project_alias(self):
        selected={'sha':dict(key='technical')}
        merge_summary_sources(selected,{'sha':dict(key='reviewed-technical')},[dict(identity_source='different-original')])
        self.assertEqual('reviewed-technical',selected['sha']['key'])
