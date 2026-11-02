args<-commandArgs(trailingOnly=TRUE)
if(length(args)!=5)stop('Require folder seed reps threshold concentration')
folder<-args[1];seed<-as.integer(args[2]);reps<-as.integer(args[3]);p<-as.numeric(args[4]);concentration<-as.numeric(args[5])
stopifnot(reps>=1,reps<=100000,concentration>0,is.finite(concentration))
script<-sub('^--file=','',grep('^--file=',commandArgs(),value=TRUE)[1])
source(file.path(dirname(script),'methods.R'))
d<-read.csv(file.path(folder,'matrix.csv'),check.names=FALSE)
criteria<-read.csv(file.path(folder,'criteria.csv'));weights<-read.csv(file.path(folder,'weights.csv'))
codes<-criteria$code;X<-as.matrix(d[,codes,drop=FALSE]);storage.mode(X)<-'double'
stopifnot(!anyDuplicated(d$project_id),!anyNA(X))
writeout<-function(rows,name)write.csv(rows,file.path(folder,paste0(name,'.csv')),row.names=FALSE,na='')
all_ranks<-all_weight<-all_rounding<-all_leave<-all_methods<-all_functions<-all_cohorts<-all_ahp<-list()
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
  set.seed(seed);W<-matrix(NA_real_,nrow(X),reps);D<-W
  lower<-as.matrix(d[,paste0(codes,'_lower'),drop=FALSE]);upper<-as.matrix(d[,paste0(codes,'_upper'),drop=FALSE])
  for(k in seq_len(reps)) {
    wt<-rgamma(length(w),shape=pmax(w*concentration,1e-9));wt<-wt/sum(wt)
    W[,k]<-rank_score(promethee(X,wt,p))
  }
  # Independent RNG stream; keeps source rounding distinct from weight uncertainty.
  set.seed(seed+1)
  for(k in seq_len(reps)) {
    XD<-matrix(runif(length(X),as.vector(lower),as.vector(upper)),nrow=nrow(X))
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
bind<-function(x,empty)if(length(x))do.call(rbind,x) else empty
writeout(bind(all_ranks,data.frame()),'ranking')
writeout(bind(all_weight,data.frame()),'weight_uncertainty')
writeout(bind(all_rounding,data.frame()),'rounding_uncertainty')
writeout(bind(all_leave,data.frame()),'leave_out')
writeout(bind(all_methods,data.frame()),'method_comparison')
writeout(bind(all_functions,data.frame()),'function_sensitivity')
writeout(bind(all_cohorts,data.frame(scenario=character(),removed_project=character(),project_id=character(),rank=double())),'cohort_sensitivity')
writeout(bind(all_ahp,data.frame()),'ahp_audit')
# True pairwise dominance on the active panel; absence of dominance is incomparability.
pairs<-list()
for(i in seq_len(nrow(X)))for(j in seq_len(nrow(X)))if(i!=j)pairs[[paste(i,j)]]<-data.frame(a=d$project_id[i],b=d$project_id[j],dominates=all(X[i,]>=X[j,])&&any(X[i,]>X[j,]))
writeout(do.call(rbind,pairs),'partial_order')
writeout(data.frame(R_version=R.version.string,seed,reps,threshold=p,concentration),'runtime')
cat('Completed',nrow(X),'resource-scoped alternatives;',length(codes),'criteria.\n')
