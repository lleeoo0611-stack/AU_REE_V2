"""Reviewed primary-page additions through the existing claims and review contracts."""
import copy,json
from pathlib import Path
from au_ree_v2.evidence import load_claims,normalize,transformation_issues
from au_ree_v2.store import filehash,append_snapshots,digest

ROOT=Path(__file__).resolve().parents[1]


def barkly(claims,review):
    from datetime import datetime,timezone
    import fitz,re
    sha='7da4404af58caddba90ef7b83c2e26c3a121b2b44e33895a45d139d30183f6ca'
    path=ROOT/'data/snapshots'/(sha+'.pdf');assert filehash(path)==sha
    source=dict(key='barkly_ipo20260130',kind='pdf',sha256=sha,path=path.relative_to(ROOT).as_posix(),
        url='https://data-api.marketindex.com.au/api/v1/announcements/XASX%3ABAK%3A6A1309514/pdf/inline/barkly-rare-earths-completes-successful-ipo',
        publication_date='2026-01-30',available_date='2026-11-05',
        acquired_at=datetime.fromtimestamp(path.stat().st_ctime,timezone.utc).isoformat(),
        capture_metadata='Recovered original-capture filesystem timestamp after concurrent manifest overwrite; original bytes/hash verified',
        company='Barkly Rare Earths Ltd',asx_code='BAK',distribution='PUBLIC_MIRROR_OF_ISSUER_ASX_ANNOUNCEMENT')
    append_snapshots(ROOT/'data/manifest.json',[source])
    (ROOT/'work/phase21/barkly_snapshot.json').write_text(json.dumps(source,indent=2),encoding='utf8')
    p=dict(id='barkly-ree',entity_namespace='project_registry_v1',name='Barkly Rare Earths Project',state='NT',
        identity_source=source['key'],required_source_keys=[source['key']],aliases=['Barkly Project'],
        identity_evidence=dict(source_sha256=sha,page=1,quote='100%-owned Barkly',
            reason='Issuer explicitly identifies its wholly owned Barkly Rare Earths Project in NT; Buntine separate, no name/proximity merge'),observations=[])
    common=dict(scope='Barkly Vanadis and Benmara combined Inferred Mineral Resource; excludes Exploration Target and Buntine',
        statement_id='barkly-resource-prospectus-20251201',category='INFERRED',effective_date='2025-12-01',
        source_key=source['key'],source_sha256=sha,pdf_page=2,page_markers=['Barkly Project rare earth element Inferred Mineral Resource','2,100','710'],
        locator='physical PDF p2 Table1 plus p1 reported contained TREO; 430ppm NdPr cutoff',basis='TREO',
        extraction_method='PRIMARY_PAGE_SCOPED_TRANSCRIPTION_NOT_INDEPENDENT_APPROVAL')
    for var,value,unit,page in [('ore_mt',40,'Mt',2),('grade',2100,'ppm',2),('contained_treo_kt',82,'kt',1)]:
        o=dict(common,variable=var,value=value,unit=unit,rounding_half_width=.5)
        if page==1:o.update(pdf_page=1,page_markers=['40 Mt','2,100 ppm','82,000 tonnes'])
        p['observations'].append(o)
    # Printed 40Mt*2100ppm=84kt conflicts with reported 82kt at the fixed
    # printed-unit intervals. Retain all three; existing QA excludes R1. Do not
    # invent broader rounding to force this new Project into a ranking panel.
    for var,value,basis in [('reported_resource_magnet_ppm',710,'PrNdDyTb_OXIDES'),('reported_resource_treo_ppm',2100,'TREO')]:
        p['observations'].append(dict(common,variable=var,value=value,unit='ppm',basis=basis,
            context_evidence=[dict(page=3,markers=['MREO ratio = (Nd2O3 + Pr6O11 + Tb4O7 + Dy2O3)/TREO'])]))
    p['observations'].append(dict(common,variable='magnet_reo_share_pct',value=100*710/2100,unit='%',basis='PrNdDyTb_OXIDES_OVER_TREO',
        transform=dict(rule='RATIO_PPM_PERCENT',inputs=['reported_resource_magnet_ppm','reported_resource_treo_ppm']),
        context_evidence=[dict(page=3,markers=['MREO ratio = (Nd2O3 + Pr6O11 + Tb4O7 + Dy2O3)/TREO'])],
        rounding_bounds=[100*709.5/2100.5,100*710.5/2099.5]))
    if not any(x['id']==p['id'] for x in claims['projects']):claims['projects'].append(p)
    identity_path=ROOT/'data/identity_links.json';identity=json.loads(identity_path.read_text(encoding='utf8'))
    for name in ('Vanadis','Benmara'):
        native='barkly-'+name.lower()
        if not any(x['id']==native for x in claims['projects']):
            claims['projects'].append(dict(id=native,entity_namespace='ISSUER_DOCUMENTED_PROSPECT',entity_kind='PROSPECT',
                name=name+' prospect within Barkly',state='NT',identity_source=source['key'],required_source_keys=[source['key']],observations=[]))
        relation=dict(left=['project_registry_v1','barkly-ree'],right=['ISSUER_DOCUMENTED_PROSPECT',native],
            relation='CONTAINS_ISSUER_DOCUMENTED_PROSPECT_NOT_RESOURCE_SUM',source_key=source['key'],source_sha256=sha,
            pdf_page=2,page_markers=['100% owned Barkly Project','Vanadis','Benmara'],
            locator='physical PDF p2 explicit drilling at Vanadis and Benmara prospects within Barkly; no resource split or addition',
            effective_date='2026-01-30',required_source_keys=[source['key']])
        if relation not in identity['relations']:identity['relations'].append(relation)
    identity_path.write_text(json.dumps(identity,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    review['sources'][source['key']]=source
    pid='AU-'+digest(['project_registry_v1','barkly-ree'])[:20]
    with fitz.open(path) as pdf:
        quote=lambda n:dict(source_key=source['key'],page=n,quote=re.sub(r'\s+',' ',pdf[n-1].get_text()).strip())
        scope=quote(1);route=quote(5)
    group=dict(project_id=pid,name=p['name'],scope=common['scope'],documents=[dict(source_key=source['key'],scope_reason='Explicit Barkly Project testwork and ownership; Buntine excluded',scope_evidence=scope)],
        search_complete=False,review_complete_items=[],stop_reason='Original IPO read; cited detailed prospectus HTTP403, no claim of exhaustive review',
        conflicts_updates=['40Mt x 2100ppm=84kt versus reported82kt; no broadened rounding or forced R1 admission'],
        items={code:dict(status='UNVERIFIABLE',reason='Detailed prospectus unavailable; required facets not fully verifiable in retrieved IPO') for code in ('TD1','TD2','TD3','TD4','TD5','TD6','TD7')})
    group['items']['TD2']=dict(status='DISCLOSED',reason='Explicit flotation then caustic pretreatment/acid leach pathway; tested upgrade and solution extraction explain provisional route selection, not feasibility',
        facets={f:dict(interpretation=reason,evidence=[route]) for f,reason in [('route','Barkly composites were floated, then caustic pretreated and acid leached; future optimisation distinguished.'),
            ('selection_reason','The source explicitly links the tested concentrate upgrade and extraction to a potential pathway to refine; not a claim of selected commercial feasibility.')]})
    if not any(g['project_id']==pid for g in review['groups']):review['groups'].append(group)
    return source


def main():
    claims,_=load_claims(ROOT,freeze=True)
    sources={s['key']:s for s in json.loads((ROOT/'results/phase20-2026-11-05/snapshot_lock.json').read_text())}
    for project_id,key,page,values,markers,bounds in [
        ('cummins-range','cummins_mre2023',2,[16.9,4.9,.2,.8],['Mineral Resource-Based Basket Price','16.9%','4.9%','0.2%','0.8%'],[22.6,23.0]),
        ('nolans-rare-earths-project','nolans_dfs2019_asx',37,[20.5,5.9,.08,.3],['Percentage Proportion of TREO in the Mineral Resources','20.5','5.9','0.08','0.3'],[26.625,26.935])]:
        p=next(p for p in claims['projects'] if p['id']==project_id);source=sources[key]
        p['observations']=[o for o in p['observations'] if not o['variable'].startswith(('reported_resource_distribution_','normalized_resource_distribution_'))
            and not (o['variable']=='magnet_reo_share_pct' and o['source_key']==key)]
        if project_id.startswith('nolans'):
            # Rebind the identical 2017 resource to the original DFS Table2,
            # not a cross-source composition exception or a resource change.
            for o in p['observations']:
                if o['variable'] in ('ore_mt','grade','ndpr_share_pct'):
                    o.update(source_key=key,source_sha256=source['sha256'],pdf_page=15,
                        page_markers=['Statement of Mineral Resources','56','2.6','26.4'],
                        locator='physical PDF p15 Table2, same 7 June 2017 Mineral Resource; excludes Ore Reserves')
        resource=next(o for o in p['observations'] if o['variable']=='ore_mt')
        common={k:copy.deepcopy(resource[k]) for k in ('scope','statement_id','effective_date')}
        common.update(source_key=key,source_sha256=source['sha256'],pdf_page=page,
            locator=f'physical PDF p{page}; resource oxide distribution TOTAL column, not recovery or price weights',
            category='NOT_APPLICABLE',domain='Strategic',material_basis='OXIDE_DISTRIBUTION_NOT_ORE_GRADE',page_markers=markers,
            extraction_method='REVIEWED_NATIVE_AND_RENDERED_TABLE_SOURCE_BOUND_TRANSCRIPTION')
        additions=[]
        for var,basis,v in zip(['nd','pr','tb','dy'],['Nd2O3','Pr6O11','Tb4O7','Dy2O3'],values):
            additions.append(dict(common,variable='reported_resource_distribution_'+var+'_ppm',basis=basis,value=v*10000,unit='ppm',
                original_value=v,original_unit='% of TREO',
                transform=dict(rule='OXIDE_DISTRIBUTION_PERCENT_TO_PPM',original_value=v,original_unit='% of TREO')))
        additions.append(dict(common,variable='normalized_resource_distribution_treo_ppm',basis='TREO',value=1000000,unit='ppm',
            derivation_status='DEFINITION_IDENTITY_NOT_REPORTED_MEASUREMENT',
            transform=dict(rule='REO_DISTRIBUTION_DENOMINATOR'),
            source_note='A fraction of total TREO is normalised to one million ppm by definition; no reported 100% measurement is invented.'))
        additions.append(dict(common,variable='reported_resource_distribution_magnet_ppm',basis='PrNdDyTb_OXIDES',
            value=sum(values)*10000,unit='ppm',transform=dict(rule='SUM_MAGNET_OXIDE_PPM',
            inputs=['reported_resource_distribution_'+v+'_ppm' for v in ('nd','pr','tb','dy')])))
        additions.append(dict(common,variable='magnet_reo_share_pct',basis='PrNdDyTb_OXIDES_OVER_TREO',
            value=sum(values),unit='%',rounding_bounds=bounds,uncertainty_type='PRINTED_OXIDE_DISTRIBUTION_ROUNDING_ONLY',
            transform=dict(rule='RATIO_PPM_PERCENT',inputs=['reported_resource_distribution_magnet_ppm','normalized_resource_distribution_treo_ppm'])))
        for o in additions:
            assert not normalize(o),(o,normalize(o))
            assert not transformation_issues(o,additions),(o,transformation_issues(o,additions))
            if o not in p['observations']:p['observations'].append(o)
    config_path=ROOT/'config/research.json';config=json.loads(config_path.read_text())
    config.update(version='research-v7-national-disclosure-incremental',candidate_version='ree-candidate-v2',disclosure_source_rounding=True)
    config_path.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    review_path=ROOT/'data/technical_disclosure_current.json'
    if not review_path.exists():
        review=json.loads((ROOT/'data/technical_disclosure_v1.json').read_text(encoding='utf8'))
        review['review_revision']='phase21-incremental-v1'
        review['parent_review_sha256']=filehash(ROOT/'data/technical_disclosure_v1.json')
        review_path.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    review=json.loads(review_path.read_text(encoding='utf8'));source=barkly(claims,review)
    review_path.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (ROOT/'data/claims.json').write_text(json.dumps(claims,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    sources_path=ROOT/'config/sources.json';registered=json.loads(sources_path.read_text(encoding='utf8'))
    if not any(s['key']==source['key'] for s in registered['sources']):registered['sources'].append({k:v for k,v in source.items() if k not in ('sha256','path','available_date','acquired_at')})
    sources_path.write_text(json.dumps(registered,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    policy_path=ROOT/'config/evidence_policy.json';policy=json.loads(policy_path.read_text())
    policy['technical_disclosure'].update(review_path='data/technical_disclosure_current.json',incremental_registry=True)
    policy_path.write_text(json.dumps(policy,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    path=ROOT/'config/discovery.json';d=json.loads(path.read_text());d['canonical_store']='work/phase5/canonical.sqlite'
    path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(oxide_observations_added=14,claims_sha256=filehash(ROOT/'data/claims.json'))))


if __name__=='__main__':main()
