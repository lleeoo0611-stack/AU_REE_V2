args<-commandArgs(trailingOnly=TRUE)
if(!length(args) %in% c(5,6,7))stop('Require folder seed reps threshold concentration [method_version] [research_analysis_version]')
version<-if(length(args)>=6)args[6] else 'legacy-position-rng-v1'
stopifnot(version %in% c('legacy-position-rng-v1','entity-keyed-rng-v2'))
deterministic<-version=='entity-keyed-rng-v2'
research_analysis<-length(args)==7
if(research_analysis)stopifnot(deterministic,args[7]=='evidence-cohort-v1')
folder<-args[1];seed<-as.integer(args[2]);reps<-as.integer(args[3]);p<-as.numeric(args[4]);concentration<-as.numeric(args[5])
stopifnot(reps>=1,reps<=100000,concentration>0,is.finite(concentration))
script<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1])
source(file.path(dirname(script),'methods.R'))
d<-read.csv(file.path(folder,'matrix.csv'),check.names=FALSE)
criteria<-read.csv(file.path(folder,'criteria.csv'));weights<-read.csv(file.path(folder,'weights.csv'))
if(deterministic) {
  d<-d[order(d$project_id,method='radix'),,drop=FALSE]
  criteria<-criteria[order(criteria$code,method='radix'),,drop=FALSE]
  weights<-weights[order(weights$scenario,weights$criterion,method='radix'),,drop=FALSE]
}
codes<-criteria$code;X<-as.matrix(d[,codes,drop=FALSE]);storage.mode(X)<-'double'
stopifnot(!anyDuplicated(d$project_id),!anyNA(X))
if('canonical_project_id' %in% names(d))stopifnot(!anyDuplicated(d$canonical_project_id))
writeout<-function(rows,name)write.csv(rows,file.path(folder,paste0(name,'.csv')),row.names=FALSE,na='')
all_ranks<-all_weight<-all_rounding<-all_leave<-all_methods<-all_functions<-all_cohorts<-all_ahp<-list()
all_contributions<-list()
for(scenario in unique(weights$scenario)) {
  wd<-weights[weights$scenario==scenario,];stopifnot(!anyDuplicated(wd$criterion))
  w<-wd$weight[match(codes,wd$criterion)];validate(X,w)
  # Assumption-derived reciprocal matrix exercises AHP, not elicited expert judgments.
  A<-outer(w,w,'/');a<-ahp(A);stopifnot(max(abs(a$weights-w/sum(w)))<1e-8)
  all_ahp[[scenario]]<-data.frame(scenario,criterion=codes,weight=a$weights,CR=a$CR,
      status='ASSUMPTION_DERIVED_MATRIX_NOT_EXPERT_ELICITATION')
  baseline<-promethee(X,w,p); ranks<-rank_score(baseline)
  all_ranks[[scenario]]<-data.frame(scenario,project_id=d$project_id,project_name=d$project_name,scope=d$scope,
      promethee=baseline,promethee_rank=ranks,saw=saw(X,w),saw_rank=rank_score(saw(X,w)),
      topsis=topsis(X,w),topsis_rank=rank_score(topsis(X,w)))
  if(research_analysis)for(j in seq_along(codes)) {
    wn<-w/sum(w)
    flow<-promethee(X[,j,drop=FALSE],1,p)
    all_contributions[[paste(scenario,codes[j])]]<-data.frame(scenario,
      project_id=d$project_id,project_name=d$project_name,criterion=codes[j],
      domain=criteria$domain[j],criterion_score=X[,j],normalized_weight=wn[j],
      saw_contribution=X[,j]*wn[j],promethee_net_flow_contribution=flow*wn[j],
      interpretation='MATHEMATICAL_SCORE_DECOMPOSITION_NOT_EXTERNAL_ASSOCIATION_OR_CAUSAL_EFFECT')
  }
  set.seed(seed);W<-matrix(NA_real_,nrow(X),reps);D<-W
  lower<-as.matrix(d[,paste0(codes,'_lower'),drop=FALSE]);upper<-as.matrix(d[,paste0(codes,'_upper'),drop=FALSE])
  inputs<-if(deterministic)keyed_inputs(d$project_id,codes,w,reps,version,seed,scenario,concentration) else NULL
  for(k in seq_len(reps)) {
    wt<-if(deterministic)inputs$weights[,k] else rgamma(length(w),shape=pmax(w*concentration,1e-9));wt<-wt/sum(wt)
    W[,k]<-rank_score(promethee(X,wt,p))
  }
  # Independent RNG stream; keeps source rounding distinct from weight uncertainty.
  set.seed(seed+1)
  for(k in seq_len(reps)) {
    XD<-if(deterministic)lower+inputs$rounding[,,k]*(upper-lower) else matrix(runif(length(X),as.vector(lower),as.vector(upper)),nrow=nrow(X))
    D[,k]<-rank_score(promethee(XD,w,p))
  }
  summarize<-function(M,label)data.frame(scenario,project_id=d$project_id,uncertainty=label,
      median=apply(M,1,median),q05=apply(M,1,quantile,.05),q95=apply(M,1,quantile,.95),
      frequency_first=rowMeans(M==1),
      frequency_top3=if(nrow(X)>=3)rowMeans(M<=3) else NA_real_,
      frequency_top5=if(nrow(X)>=5)rowMeans(M<=5) else NA_real_,
      interpretation='Preference/model frequency; not development success probability')
  all_weight[[scenario]]<-summarize(W,'WEIGHTS_ONLY')
  all_rounding[[scenario]]<-summarize(D,'SOURCE_ROUNDING_ONLY_NOT_MEASUREMENT_UNCERTAINTY')
  if('uncertainty_kind' %in% names(d) && all(d$uncertainty_kind=='NO_SOURCE_BOUNDS')) {
    all_rounding[[scenario]]$uncertainty<-'NOT_QUANTIFIED_NO_SOURCE_BOUNDS'
    for(column in c('median','q05','q95','frequency_first','frequency_top3','frequency_top5'))all_rounding[[scenario]][[column]]<-NA_real_
  }
  for(j in seq_along(codes)) {
    idx<-setdiff(seq_along(codes),j)
    if(!length(idx)||sum(w[idx])<=0)next
    rr<-rank_score(promethee(X[,idx,drop=FALSE],w[idx],p))
    all_leave[[paste(scenario,j)]]<-data.frame(scenario,type='criterion',removed=codes[j],project_id=d$project_id,rank=rr,rank_change=rr-ranks)
  }
  for(domain in unique(criteria$domain)) {
    idx<-which(criteria$domain!=domain)
    if(!length(idx)||sum(w[idx])<=0)next
    rr<-rank_score(promethee(X[,idx,drop=FALSE],w[idx],p))
    all_leave[[paste(scenario,domain)]]<-data.frame(scenario,type='domain',removed=domain,project_id=d$project_id,rank=rr,rank_change=rr-ranks)
  }
  all_methods[[scenario]]<-data.frame(scenario,comparison=c('PROMETHEE_vs_SAW','PROMETHEE_vs_TOPSIS','SAW_vs_TOPSIS'),
      spearman=c(safe_cor(ranks,rank_score(saw(X,w))),safe_cor(ranks,rank_score(topsis(X,w))),safe_cor(rank_score(saw(X,w)),rank_score(topsis(X,w)))))
  alt<-as.matrix(d[,paste0(codes,'_alt'),drop=FALSE])
  for(mult in c(.5,1,2))all_functions[[paste(scenario,mult)]]<-data.frame(scenario,variant=paste0('threshold_x',mult),project_id=d$project_id,rank=rank_score(promethee(X,w,p*mult)))
  all_functions[[paste(scenario,'linear')]]<-data.frame(scenario,variant='linear_resource_anchor',project_id=d$project_id,rank=rank_score(promethee(alt,w,p)))
  for(i in seq_len(nrow(X))) {
    idx<-setdiff(seq_len(nrow(X)),i)
    if(length(idx)<2)next
    all_cohorts[[paste(scenario,i)]]<-data.frame(scenario,removed_project=d$project_id[i],project_id=d$project_id[idx],rank=rank_score(promethee(X[idx,,drop=FALSE],w,p)))
  }
}
# Independent preference sweep on the existing R1/C1 candidate panel.
# Offtake filters evidence coverage only; it is never a score or zero fill.
if(deterministic && setequal(codes,c('R1','C1'))) {
  coverage<-read.csv(file.path(folder,'..','commercial_project_coverage.csv'))
  has_offtake<-coverage$offtake_evidence[match(d$project_id,coverage$project_id)]>0
  cohorts<-list(FINANCING_DISCLOSURE=seq_len(nrow(X)),FINANCING_AND_OFFTAKE=which(has_offtake))
  sweep_rows<-thresholds<-list()
  for(cohort in names(cohorts)) {
    idx<-cohorts[[cohort]];if(length(idx)<2)next
    Z<-X[idx,,drop=FALSE]
    for(cw in sort(unique(c(0,1/11,.1386,.14,seq(.05,.95,.05),1)))) {
      ww<-ifelse(codes=='C1',cw,1-cw)
      scores<-list(SAW=saw(Z,ww),PROMETHEE_II=promethee(Z,ww,p),TOPSIS=topsis(Z,ww))
      for(method in names(scores))sweep_rows[[length(sweep_rows)+1]]<-data.frame(cohort,n=length(idx),commercial_weight=cw,method,project_id=d$project_id[idx],project_name=d$project_name[idx],score=scores[[method]],rank=rank_score(scores[[method]]))
    }
    for(i in seq_len(nrow(Z)-1))for(j in seq.int(i+1,nrow(Z))) {
      dr<-Z[i,'R1']-Z[j,'R1'];dc<-Z[i,'C1']-Z[j,'C1']
      cross<-if(dr==dc)NA_real_ else dr/(dr-dc)
      if(!is.na(cross) && cross>=0 && cross<=1)thresholds[[length(thresholds)+1]]<-data.frame(cohort,a=d$project_id[idx[i]],a_name=d$project_name[idx[i]],b=d$project_id[idx[j]],b_name=d$project_name[idx[j]],saw_crossing_commercial_weight=cross,interpretation='PAIRWISE_EQUALITY_NOT_RECOMMENDED_WEIGHT_OR_GLOBAL_WINNER_GUARANTEE')
    }
  }
  writeout(do.call(rbind,sweep_rows),'commercial_weight_sensitivity')
  if(length(thresholds))writeout(do.call(rbind,thresholds),'commercial_saw_crossings')
}

bind<-function(x,empty)if(length(x))do.call(rbind,x) else empty
writeout(bind(all_ranks,data.frame()),'ranking')
writeout(bind(all_weight,data.frame()),'weight_uncertainty')
writeout(bind(all_rounding,data.frame()),'rounding_uncertainty')
writeout(bind(all_leave,data.frame()),'leave_out')
writeout(bind(all_methods,data.frame()),'method_comparison')
writeout(bind(all_functions,data.frame()),'function_sensitivity')
writeout(bind(all_cohorts,data.frame(scenario=character(),removed_project=character(),project_id=character(),rank=double())),'cohort_sensitivity')
writeout(bind(all_ahp,data.frame()),'ahp_audit')
if(research_analysis) {
  writeout(bind(all_contributions,data.frame()),'criterion_contributions')
  # Hold shared criteria and their weights fixed while changing the reference
  # population. Rerank the broad scores on the common Projects before comparing
  # with the common-cohort refit, so merely removing competitors is not called
  # a pairwise reversal. Then change criteria/weight allocation on that same set.
  candidates<-list()
  for(path in sort(list.dirs(dirname(folder),recursive=FALSE))) {
    if(normalizePath(path,winslash='/',mustWork=FALSE)==normalizePath(folder,winslash='/',mustWork=FALSE))next
    files<-file.path(path,c('matrix.csv','criteria.csv','weights.csv'))
    if(!all(file.exists(files)))next
    bd<-read.csv(files[1],check.names=FALSE);bc<-read.csv(files[2]);bw<-read.csv(files[3])
    if(!all(c('project_id','scope') %in% names(bd)) || anyDuplicated(bd$project_id) ||
       nrow(bd)<nrow(d) || anyDuplicated(bc$code))next
    shared<-sort(intersect(codes,bc$code));if(!length(shared))next
    # A code alone does not establish an identical scoring definition.
    fields<-c('code','domain','direction','low','high','function.')
    if(!all(fields %in% names(bc)) || !all(fields %in% names(criteria)))next
    shared<-shared[vapply(shared,function(code) {
      a<-criteria[match(code,criteria$code),fields];b<-bc[match(code,bc$code),fields]
      identical(as.character(unlist(a,use.names=FALSE)),as.character(unlist(b,use.names=FALSE)))
    },logical(1))]
    if(!length(shared))next
    ids<-which(d$project_id %in% bd$project_id)
    bi<-match(d$project_id[ids],bd$project_id)
    valid<-!is.na(d$scope[ids]) & !is.na(bd$scope[bi]) & d$scope[ids]==bd$scope[bi]
    if('canonical_project_id' %in% names(d) && 'canonical_project_id' %in% names(bd))
      valid<-valid & !is.na(d$canonical_project_id[ids]) & !is.na(bd$canonical_project_id[bi]) &
        d$canonical_project_id[ids]==bd$canonical_project_id[bi]
    for(code in shared)valid<-valid & !is.na(bd[[code]][bi]) &
      d[[code]][ids]==bd[[code]][bi]
    ids<-ids[which(valid)];bi<-match(d$project_id[ids],bd$project_id)
    if(length(ids)<2)next
    # Equal-size panels are useful only when their criterion sets differ.
    if(nrow(bd)==nrow(d) && setequal(shared,codes) && setequal(codes,bc$code))next
    candidates[[length(candidates)+1]]<-list(path=path,d=bd,criteria=bc,weights=bw,
      shared=shared,ids=ids,bi=bi)
  }
  comparisons<-list()
  if(length(candidates)) {
    # Choose one reproducible broad reference: most alternatives, then largest
    # comparable intersection, then most shared criteria and stable panel name.
    pick<-order(-vapply(candidates,function(x)nrow(x$d),integer(1)),
      -vapply(candidates,function(x)length(x$ids),integer(1)),
      -vapply(candidates,function(x)length(x$shared),integer(1)),
      vapply(candidates,function(x)basename(x$path),character(1)))[1]
    ref<-candidates[[pick]];ids<-ref$ids;bi<-ref$bi
    BX<-as.matrix(ref$d[,ref$shared,drop=FALSE]);storage.mode(BX)<-'double'
    CX<-BX[bi,,drop=FALSE];TX<-X[ids,,drop=FALSE]
    method_scores<-function(Z,ww)list(SAW=saw(Z,ww),PROMETHEE_II=promethee(Z,ww,p),TOPSIS=topsis(Z,ww))
    for(scenario in unique(weights$scenario)) {
      bws<-ref$weights[ref$weights$scenario==scenario,]
      tws<-weights[weights$scenario==scenario,]
      wb<-bws$weight[match(ref$shared,bws$criterion)]
      wt<-tws$weight[match(codes,tws$criterion)]
      if(anyNA(wb)||anyNA(wt)||sum(wb)<=0||sum(wt)<=0)next
      broad<-method_scores(BX,wb);common<-method_scores(CX,wb)
      target<-method_scores(TX,wt);full_target<-method_scores(X,wt)
      for(method in names(broad)) {
        a<-broad[[method]][bi];b<-common[[method]];c<-target[[method]]
        comparisons[[paste(scenario,method)]]<-data.frame(scenario,method,
          baseline_panel=basename(ref$path),target_panel=basename(folder),
          baseline_n=nrow(BX),target_n=nrow(X),common_n=length(ids),
          shared_criteria=paste(ref$shared,collapse='|'),target_criteria=paste(codes,collapse='|'),
          project_id=d$project_id[ids],project_name=d$project_name[ids],scope=d$scope[ids],
          broad_shared_score=a,broad_shared_rank=rank_score(broad[[method]])[bi],
          broad_shared_rank_on_common=rank_score(a),common_shared_score=b,
          common_shared_rank=rank_score(b),cohort_reference_score_change=b-a,
          cohort_reference_rank_change=rank_score(b)-rank_score(a),
          common_target_score=c,common_target_rank=rank_score(c),
          criteria_and_weight_rank_change=rank_score(c)-rank_score(b),
          full_target_rank=rank_score(full_target[[method]])[ids],
          full_target_rank_on_common=rank_score(full_target[[method]][ids]),
          evidence_match='IDENTICAL_SCOPE_SCORING_DEFINITION_SHARED_SCORES',
          interpretation='OBSERVED_SELECTION_AND_MODEL_EFFECTS_NOT_MISSINGNESS_MECHANISM_OR_CAUSAL_EFFECT')
      }
    }
  }
  if(length(comparisons))writeout(do.call(rbind,comparisons),'evidence_cohort_sensitivity')
}
# True pairwise dominance on the active panel; absence of dominance is incomparability.
pairs<-list()
for(i in seq_len(nrow(X)))for(j in seq_len(nrow(X)))if(i!=j)pairs[[paste(i,j)]]<-data.frame(a=d$project_id[i],b=d$project_id[j],dominates=all(X[i,]>=X[j,])&&any(X[i,]>X[j,]))
writeout(do.call(rbind,pairs),'partial_order')

# An external descriptive factor for the exploratory WA resource-only ranking.
# Development stage is not in the two scoring criteria. Its association is
# cross-sectional, source-selected and cannot be interpreted causally.
if('official_status' %in% names(d)) {
  stopifnot(all(c('raw_contained_treo_kt','raw_grade_pct','source_sha256','source_locator') %in% names(d)))
  stage_code<-c(Exploration=1,Scoping=2,Feasibility=3,Operating=4)
  ordinal<-as.numeric(stage_code[as.character(d$official_status)])
  stopifnot(!anyNA(ordinal))
  associations<-list()
  for(nm in names(all_ranks)) {
    rr<-all_ranks[[nm]]
    stopifnot(identical(as.character(rr$project_id),as.character(d$project_id)))
    rho<-if(length(unique(ordinal))<2 || sd(rr$promethee_rank)==0) NA_real_
         else cor(ordinal,-rr$promethee_rank,method='spearman')
    associations[[nm]]<-data.frame(scenario=nm,project_id=d$project_id,
      project_name=d$project_name,official_stage=d$official_status,
      stage_ordinal=ordinal,rank=rr$promethee_rank,
      source_treo_kt=d$raw_contained_treo_kt,
      source_grade_pct=d$raw_grade_pct,
      source_sha256=d$source_sha256,locator=d$source_locator,
      stage_rank_spearman_rho=rho,
      interpretation='Descriptive external stage association with resource-only screen; no causal or development-success inference')
  }
  writeout(do.call(rbind,associations),'aim_c_stage_rank_association')
}
if('deposit_type' %in% names(d)) {
  hostrows<-list()
  for(nm in names(all_ranks)) {
    rr<-all_ranks[[nm]]
    for(host in unique(d$deposit_type[!is.na(d$deposit_type) & nzchar(d$deposit_type)])) {
      idx<-which(d$deposit_type==host)
      hostrows[[paste(nm,host)]]<-data.frame(scenario=nm,deposit_type=host,n=length(idx),
        median_rank=median(rr$promethee_rank[idx]),min_rank=min(rr$promethee_rank[idx]),
        max_rank=max(rr$promethee_rank[idx]),sample_n=nrow(d),
        interpretation='External host-type descriptive contrast; small selected sample, no significance or causal claim')
    }
  }
  if(length(hostrows))writeout(do.call(rbind,hostrows),'aim_c_host_type_description')
}
runtime<-data.frame(R_version=R.version.string,seed,reps,threshold=p,concentration)
if(deterministic)runtime<-cbind(runtime,method_version=version,RNG_kind="L'Ecuyer-CMRG",normal_kind='Inversion',sample_kind='Rejection',identity='version|seed|scenario|family|project_id|criterion_id|draw_index',rounding='SOURCE_ROUNDING_NOT_MEASUREMENT')
if(research_analysis)runtime<-cbind(runtime,research_analysis_version=args[7])
writeout(runtime,'runtime')
cat('Completed',nrow(X),'alternatives on the frozen panel;',length(codes),'criteria.\n')
