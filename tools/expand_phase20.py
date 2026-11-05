"""Source-reviewed additions to the existing claims contract, no new database."""
import copy
import json
from pathlib import Path
from au_ree_v2.store import filehash
from au_ree_v2.evidence import load_claims,normalize,transformation_issues

ROOT=Path(__file__).resolve().parents[1]

def main():
    claims,_=load_claims(ROOT,freeze=True)
    goschen=next(p for p in claims['projects'] if p['id']=='goschen')
    resource=next(o for o in goschen['observations'] if o['variable']=='contained_treo_kt')
    common={k:copy.deepcopy(resource[k]) for k in ('scope','statement_id','effective_date','source_key','source_sha256','pdf_page','locator')}
    common.update(category='NOT_APPLICABLE',material_basis='THM_PHASE_SAME_ROW_RATIO_NOT_BULK_ORE_GRADE',
        page_markers=['Pr6O11','Nd2O3','Tb4O7','Dy2O3','0.12','0.43','0.01','0.07','2.8'],
        extraction_method='REVIEWED_NATIVE_TEXT_AND_RENDERED_P12_AREA1_TOTAL_ROW',
        source_note='Area1 Table8 total; ppm converted from THM-phase percent. Same material factor cancels in oxide/TREO ratio. No reserve/other-area aggregation.')
    observations=[]
    for var,basis,value in [('reported_thm_pr_ppm','Pr6O11',1200),('reported_thm_nd_ppm','Nd2O3',4300),
                            ('reported_thm_tb_ppm','Tb4O7',100),('reported_thm_dy_ppm','Dy2O3',700),
                            ('reported_thm_treo_ppm','TREO',28000)]:
        observations.append(dict(common,variable=var,basis=basis,value=value,unit='ppm'))
    observations.append(dict(common,variable='reported_thm_magnet_ppm',basis='PrNdDyTb_OXIDES',value=6300,unit='ppm',
        transform=dict(rule='SUM_MAGNET_OXIDE_PPM',inputs=['reported_thm_pr_ppm','reported_thm_nd_ppm','reported_thm_tb_ppm','reported_thm_dy_ppm'])))
    observations.append(dict(common,variable='magnet_reo_share_pct',basis='PrNdDyTb_OXIDES_OVER_TREO',value=22.5,unit='%',
        rounding_bounds=[100*.61/2.85,100*.65/2.75],uncertainty_type='PRINTED_COMPONENT_ROUNDING_ONLY_NOT_MEASUREMENT_ERROR',
        transform=dict(rule='RATIO_PPM_PERCENT',inputs=['reported_thm_magnet_ppm','reported_thm_treo_ppm'])))
    for o in observations:
        assert not normalize(o),normalize(o)
        assert not transformation_issues(o,observations),transformation_issues(o,observations)
        if o not in goschen['observations']:goschen['observations'].append(o)
    source=next(s for s in json.loads((ROOT/'data/manifest.json').read_text())['snapshots'] if s['key']=='koppamurra_pfs2026')
    assert filehash(ROOT/source['path'])==source['sha256']
    event=dict(event_id='koppamurra-project-funding-plan-20260625',project_namespace='SA_MINING_PROJECT_SITE_NO',
        project_native_id='2298466',source_key=source['key'],source_sha256=source['sha256'],pdf_page=62,
        page_markers=['Project Funding','No binding commitment has been received','commenced discussions with potential financiers'],
        locator='Physical PDF p62 / printed p42; Koppamurra PFS Project Funding',effective_date='2026-06-25',
        scope='Koppamurra PFS project development funding plan; not secured funds or corporate cash',
        event_type='FINANCING',attribution='PROJECT',valid_from=None,valid_to=None,
        finance_state='PLANNED_OR_NONBINDING',facility_id='koppamurra-project-funding-plan',
        conditions_status='PLANNING_NO_FULL_BINDING_COMMITMENT',agreement_state='DISCUSSIONS_ONLY',
        conditions='Further studies, approvals, market conditions and final investment decision; no certainty of funding',
        currentness='DATED_DISCLOSURE_NOT_CERTIFICATION_OF_CURRENT_AVAILABILITY')
    if event not in claims['events']:claims['events'].append(event)
    (ROOT/'data/claims.json').write_text(json.dumps(claims,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    path=ROOT/'config/research.json';config=json.loads(path.read_text())
    config.update(version='research-v6-current-disclosure-evidence',disclosure_current_baseline=True)
    config['cohorts']['full_evidence']='Resource-defined cohort with all six scored criteria; transparency replaces technical performance. No legacy recovery entry gate. Not formal C1 approval.'
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(added_oxide_observations=7,added_project_funding_events=1,claims_sha256=filehash(ROOT/'data/claims.json'))))

if __name__=='__main__':main()
