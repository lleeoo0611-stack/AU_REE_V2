"""Rank and export disclosure panels from their assessed evidence and baseline."""

from pathlib import Path

from .mcda import interval_mcda
from .store import canonical
from .tabular import write_csv

DISCLOSURE_VERSION = 'technical-disclosure-transparency-v1'


def prepare_disclosure_analysis(result, baseline, config, out):
    """Use the existing interval engine and R interchange; no imputation.

    Non-Technical scores are frozen outputs of this module's prior prepare(),
    retaining raw values, provenance and declared cohort scope. They are not
    silently recomputed under a different source selection or normalization.
    """
    out=Path(out);codes=list(config['panels']['six_domain'])
    criteria={c['code']:c for c in config['criteria']};scores=sorted(result['scores'],key=lambda s:s['project_id'])
    originals=baseline['scores'];matrices=[];ranking=[];weights=[];changes=[]
    prepared={'panels':{}};p=config['promethee_threshold']
    for s in scores:
        row=dict(project_id=s['project_id'],project_name=s['project_name'],scope=s['scope'])
        for code in codes:
            entry=originals.get(s['project_id'],{}).get(code)
            lo,hi=(s['score_lower']/100,s['score_upper']/100) if code=='T1' else ((entry['score'],entry['score']) if entry else (0,1))
            row[code+'_lower']=lo;row[code+'_upper']=hi
            row[code]=lo if abs(hi-lo)<1e-12 else None
        matrices.append(row)
    write_csv(out/'disclosure_composite_matrix.csv',matrices,list(matrices[0]))
    point=[r for r in matrices if all(r[c] is not None for c in codes)]
    # Full 31-group outer possibility sets. No stochastic draws over unknown
    # disclosures, no per-case redistribution, and no artificial tie breaking.
    for scenario,dw in sorted(config['scenarios'].items()):
        original=dw['Technical'];variants={'baseline':original,'without_T':0.,
            **{'T_'+str(int(t*100)):t for t in (.05,.1,.2,.3)}}
        for variant,t in variants.items():
            ww=[t if criteria[c]['domain']=='Technical' else dw[criteria[c]['domain']]*(1-t)/(1-original) for c in codes]
            for remove_d in (False,True) if variant in ('baseline','without_T') else (False,):
                w=list(ww);label=variant+('_without_D' if remove_d else '')
                if remove_d:
                    w[codes.index('D1')]=0;total=sum(w);w=[v/total for v in w]
                weights.extend(dict(scenario=scenario,variant=label,criterion=c,weight=v) for c,v in zip(codes,w))
                bounds=[[(r[c+'_lower'],r[c+'_upper']) for c in codes] for r in matrices]
                for method,rr in interval_mcda(bounds,w,p).items():
                    for row,r in zip(matrices,rr):ranking.append(dict(scenario=scenario,variant=label,method=method,
                        project_id=row['project_id'],project_name=row['project_name'],**r,
                        all_six_known=all(row[c] is not None for c in codes)))
    # Transparent-only comparisons on all groups, including explicit unknowns.
    tr=interval_mcda([[(s['score_lower']/100,s['score_upper']/100)] for s in scores],[1],p)
    ranks=[dict(**{k:v for k,v in s.items() if k not in ('score_lower','score_upper')},
                disclosure_lower_pct=s['score_lower'],disclosure_upper_pct=s['score_upper'],**r)
           for s,r in zip(scores,tr['SAW'])]
    observed=[s for s in scores if s['score'] is not None]
    for row in ranks:
        value=row['score']
        row['known_subset_n']=len(observed)
        row['known_subset_tied_rank']=None if value is None else 1+sum(s['score']>value+1e-12 for s in observed)+.5*(sum(abs(s['score']-value)<1e-12 for s in observed)-1)
    write_csv(out/'disclosure_ranking.csv',ranks,list(ranks[0]))
    write_csv(out/'disclosure_composite_ranking.csv',ranking,list(ranking[0]))
    write_csv(out/'disclosure_weights.csv',weights,list(weights[0]))
    sensitivity=[]
    by_key={(r['scenario'],r['variant'],r['method'],r['project_id']):r for r in ranking}
    for scenario,variant,method in sorted({(r['scenario'],r['variant'],r['method']) for r in ranking}):
        rr=[by_key[scenario,variant,method,s['project_id']] for s in scores]
        original_rows=[by_key[scenario,'baseline',method,s['project_id']] for s in scores]
        sensitivity.append(dict(scenario=scenario,variant=variant,method=method,groups=len(rr),
            changed_rank_envelopes=sum((a['rank_best'],a['rank_worst'])!=(b['rank_best'],b['rank_worst']) for a,b in zip(rr,original_rows)),
            min_rank_width=min(r['rank_worst']-r['rank_best'] for r in rr),
            max_rank_width=max(r['rank_worst']-r['rank_best'] for r in rr),
            sufficient_ordered_pairs=sum(a['score_lower']>b['score_upper']+1e-12 for i,a in enumerate(rr) for j,b in enumerate(rr) if i!=j),
            interpretation='Outer possibility envelopes; unknown disclosures are not sampled'))
    write_csv(out/'disclosure_interval_sensitivity.csv',sensitivity,list(sensitivity[0]))
    # A common observed subset isolates the effect of T. Same alternatives
    # with/without T; no case is admitted by filling its other missing domains.
    panels=config['evidence_resolution']['technical_disclosure']['panels']
    for panel,cc in panels.items():
        rr=[]
        for r in matrices:
            if not all(r[c] is not None for c in cc):continue
            row={k:r[k] for k in ('project_id','project_name','scope')}
            row['uncertainty_kind']='NO_SOURCE_BOUNDS'
            for c in cc:
                for suffix in ('','_lower','_upper','_alt'):row[c+suffix]=r[c]
                entry=originals.get(r['project_id'],{}).get(c,{})
                if config.get('disclosure_source_rounding'):
                    row[c+'_lower']=entry.get('score_lower',r[c]);row[c+'_upper']=entry.get('score_upper',r[c])
                    row[c+'_alt']=entry.get('score_alt',r[c])
                    row['uncertainty_kind']='SOURCE_ROUNDING_ONLY_NOT_MEASUREMENT_ERROR'
            rr.append(row)
        folder=out/panel;prepared['panels'][panel]=len(rr)
        write_csv(folder/'matrix.csv',rr,list(rr[0]) if rr else ['project_id','project_name','scope',*cc])
        write_csv(folder/'criteria.csv',[criteria[c] for c in cc],['code','domain','direction','low','high','function','definition_version'])
        ww=[]
        for scenario,dw in sorted(config['scenarios'].items()):
            active=[dw[criteria[c]['domain']] for c in cc];total=sum(active)
            for label,w in [('with_T',[v/total for v in active]),('without_T',[0 if c=='T1' else v for c,v in zip(cc,active)])]:
                if sum(w)<=0:continue
                w=[v/sum(w) for v in w]
                ww.extend(dict(scenario=scenario+'_'+label,criterion=c,weight=v) for c,v in zip(cc,w))
        write_csv(folder/'weights.csv',ww,['scenario','criterion','weight'])
    # Descriptive D overlap only on pairs with a point disclosure score.
    overlap=[dict(project_id=r['project_id'],project_name=r['project_name'],
                  T1=r['T1'],D1=r['D1']) for r in matrices if r['T1'] is not None and r['D1'] is not None]
    write_csv(out/'disclosure_development_overlap.csv',overlap,['project_id','project_name','T1','D1'])
    from statistics import correlation,StatisticsError
    def tied_ranks(values):return [1+sum(v>x for v in values)+.5*(sum(v==x for v in values)-1) for x in values]
    try:
        rho=correlation(tied_ranks([r['T1'] for r in overlap]),tied_ranks([r['D1'] for r in overlap])) if len(overlap)>=3 else None
    except StatisticsError:rho=None
    summary=dict(version=DISCLOSURE_VERSION,groups=len(scores),point_disclosure=sum(s['score'] is not None for s in scores),
        full_six_point_n=len(point),panels=prepared['panels'],D_overlap_n=len(overlap),D_overlap_spearman=rho,
        D_overlap_interpretation='DESCRIPTIVE_PAIRED_SCORES_ONLY_NOT_CAUSAL_OR_INDEPENDENCE_TEST',
        ranking_interpretation='COMPOSITE_INCLUDING_INFORMATION_TRANSPARENCY_NOT_TECHNICAL_CAPABILITY',
        interval_interpretation='CONSERVATIVE_OUTER_POSSIBILITY_BOUNDS_NOT_CONFIDENCE_OR_PROBABILITIES',
        formal_C1='UNCHANGED_GATES_NOT_AUTO_ADMITTED',baseline_version=baseline['version'])
    (out/'disclosure_analysis.json').write_text(canonical(summary)+'\n',encoding='utf8')
    return prepared,summary
