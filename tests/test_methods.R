source('R/methods.R')
X<-rbind(c(1,1),c(0,0),c(.5,.5));w<-c(.5,.5)
stopifnot(identical(order(-promethee(X,w)),c(1L,3L,2L)))
stopifnot(max(abs(saw(X,w)-c(1,0,.5)))<1e-9)
stopifnot(max(abs(topsis(X,w)-c(1,0,.5)))<1e-9)
stopifnot(abs(ahp(outer(c(.6,.3,.1),c(.6,.3,.1),'/'))$CR)<1e-8)
bad<-matrix(c(1,9,1/9,1/9,1,9,9,1/9,1),3)
stopifnot(inherits(try(ahp(bad),silent=TRUE),'try-error'))
tie<-matrix(.5,3,2)
stopifnot(all(promethee(tie,w)==0),all(topsis(tie,w)==.5))
stopifnot(inherits(try(promethee(matrix(NA_real_,2,2),w),silent=TRUE),'try-error'))
cat('R analytical invariants passed\n')

# Identity-keyed uniforms survive both permutations and cohort changes.
a<-keyed_inputs(c('a','b','c'),c('R1','C1'),c(.7,.3),20,'entity-keyed-rng-v2',42,'s',30)
b<-keyed_inputs(c('c','a','b'),c('C1','R1'),c(.3,.7),20,'entity-keyed-rng-v2',42,'s',30)
stopifnot(identical(a$rounding,b$rounding[c(2,3,1),c(2,1),,drop=FALSE]))
stopifnot(identical(a$weights,b$weights[c(2,1),,drop=FALSE]))
c<-keyed_inputs(c('b','d'),c('R1','C1'),c(.7,.3),20,'entity-keyed-rng-v2',42,'s',30)
stopifnot(identical(a$rounding[2,,],c$rounding[1,,]))
set.seed(123);state<-.Random.seed
u<-keyed_uniform(10,'v',1,'s','SOURCE_ROUNDING','p','c')
stopifnot(identical(state,.Random.seed),identical(u,keyed_uniform(10,'v',1,'s','SOURCE_ROUNDING','p','c')))
stopifnot(!identical(u,keyed_uniform(10,'v',1,'s','WEIGHTS','p','c')))
cat('Identity RNG invariants passed\n')

# Phase12 analysis reuses the same engine, separates reference-population and
# criterion/weight effects, and never treats mismatched resource scopes as data.
analysis_tmp<-tempfile('evidence-cohort-');dir.create(analysis_tmp)
on.exit_cleanup<-function()unlink(analysis_tmp,recursive=TRUE)
baseline_folder<-file.path(analysis_tmp,'broad');target_folder<-file.path(analysis_tmp,'target')
dir.create(baseline_folder);dir.create(target_folder)
base<-data.frame(project_id=letters[1:5],canonical_project_id=letters[1:5],
  project_name=LETTERS[1:5],scope=paste0('resource-',letters[1:5]),
  R1=c(.9,.7,.5,.3,.2),I4=c(.1,.8,.9,.2,.95))
target<-base[1:4,];target$S1<-c(.3,.7,.4,.6)
target$scope[4]<-'different-mine-plan'
make_panel<-function(folder,m,codes) {
  for(code in codes)for(suffix in c('_lower','_upper','_alt'))m[[paste0(code,suffix)]]<-m[[code]]
  write.csv(m,file.path(folder,'matrix.csv'),row.names=FALSE)
  cc<-data.frame(code=c('R1','I4','S1'),domain=c('Resource','Infrastructure','Strategic'),
    direction='MAX',low=0,high=1,`function`='linear',check.names=FALSE)
  write.csv(cc[match(codes,cc$code),],file.path(folder,'criteria.csv'),row.names=FALSE)
  ww<-c(R1=.5,I4=.3,S1=.2)[codes];ww<-ww/sum(ww)
  write.csv(do.call(rbind,lapply(c('resource','development','strategic'),function(s)
    data.frame(scenario=s,criterion=codes,weight=unname(ww)))),
    file.path(folder,'weights.csv'),row.names=FALSE)
}
make_panel(baseline_folder,base,c('R1','I4'))
make_panel(target_folder,target,c('R1','I4','S1'))
rscript_path<-file.path(R.home('bin'),if(.Platform$OS.type=='windows')'Rscript.exe' else 'Rscript')
run_fixture<-function(extra=character()) {
  log<-system2(rscript_path,c(shQuote(normalizePath('R/run_mcda.R')),
    shQuote(target_folder),'42','4','.2','30','entity-keyed-rng-v2',extra),stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(log,'status')))stop(paste(log,collapse='\n'))
}
run_fixture()
old_names<-list.files(target_folder,pattern='\\.csv$',full.names=TRUE)
old_bytes<-lapply(old_names,function(path)readBin(path,'raw',n=file.info(path)$size))
names(old_bytes)<-basename(old_names)
stopifnot(!file.exists(file.path(target_folder,'criterion_contributions.csv')))
run_fixture('evidence-cohort-v1')
for(name in setdiff(names(old_bytes),'runtime.csv'))stopifnot(identical(old_bytes[[name]],
  readBin(file.path(target_folder,name),'raw',n=file.info(file.path(target_folder,name))$size)))
cohort<-read.csv(file.path(target_folder,'evidence_cohort_sensitivity.csv'))
stopifnot(nrow(cohort)==27,all(cohort$baseline_n==5),all(cohort$target_n==4),
  all(cohort$common_n==3),setequal(cohort$project_id,letters[1:3]),
  all(cohort$shared_criteria=='I4|R1'),all(cohort$evidence_match=='IDENTICAL_SCOPE_SCORING_DEFINITION_SHARED_SCORES'))
fixed<-cohort$method %in% c('SAW','TOPSIS')
stopifnot(all(abs(cohort$cohort_reference_score_change[fixed])<1e-14),
  all(cohort$cohort_reference_rank_change[fixed]==0))
contrib<-read.csv(file.path(target_folder,'criterion_contributions.csv'))
ranks<-read.csv(file.path(target_folder,'ranking.csv'))
stopifnot(nrow(contrib)==36)
for(i in seq_len(nrow(ranks))) {
  rows<-contrib[contrib$project_id==ranks$project_id[i] & contrib$scenario==ranks$scenario[i],]
  stopifnot(abs(sum(rows$saw_contribution)-ranks$saw[i])<1e-12,
    abs(sum(rows$promethee_net_flow_contribution)-ranks$promethee[i])<1e-12,
    abs(sum(rows$normalized_weight)-1)<1e-12)
}
# Same code with a different anchor is not a comparable shared criterion.
cc<-read.csv(file.path(baseline_folder,'criteria.csv'));cc$high[cc$code=='R1']<-2
write.csv(cc,file.path(baseline_folder,'criteria.csv'),row.names=FALSE)
unlink(file.path(target_folder,'evidence_cohort_sensitivity.csv'))
run_fixture('evidence-cohort-v1')
cohort<-read.csv(file.path(target_folder,'evidence_cohort_sensitivity.csv'))
stopifnot(all(cohort$shared_criteria=='I4'))
base$scope<-paste0('unrelated-',base$scope)
make_panel(baseline_folder,base,c('R1','I4'))
unlink(file.path(target_folder,'evidence_cohort_sensitivity.csv'))
run_fixture('evidence-cohort-v1')
stopifnot(!file.exists(file.path(target_folder,'evidence_cohort_sensitivity.csv')))
on.exit_cleanup()
cat('Evidence cohort and mathematical contribution invariants passed\n')

# Excluded technical criteria remain zero in weight uncertainty, not tiny random weights.
z<-keyed_inputs(c('a','b'),c('I4','TPR','TPG'),c(1,0,0),25,'entity-keyed-rng-v2',42,'zero',30)
stopifnot(all(z$weights[1,]==1),all(z$weights[2:3,]==0))
cat('Zero-weight exclusion invariant passed\n')

bw<-budget_weights(c(.9,.02,.08),c('Reference','Technical','Technical'),c(.6,.4,.4))
stopifnot(abs(bw[1]-.6)<1e-12,abs(sum(bw[2:3])-.4)<1e-12)
cat('Technical group budget invariant passed\n')
