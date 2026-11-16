# Algorithms adapted from AU_REE/R/run_mcda.R at 093d724; no package dependencies.
# Input is a fixed-anchor benefit score matrix in [0,1].
validate <- function(X,w) {
  stopifnot(is.matrix(X), nrow(X)>=2, ncol(X)==length(w), all(is.finite(X)),
            all(X>=0 & X<=1), all(is.finite(w)), all(w>=0), sum(w)>0)
}
promethee <- function(X,w,p=.2) {
  validate(X,w); stopifnot(is.finite(p),p>0); w<-w/sum(w)
  total<-matrix(0,nrow(X),nrow(X))
  for(j in seq_len(ncol(X))) total<-total+w[j]*pmin(1,pmax(0,outer(X[,j],X[,j],'-')/p))
  (rowSums(total)-colSums(total))/(nrow(X)-1)
}
saw <- function(X,w) {validate(X,w);as.vector(X%*%(w/sum(w)))}
topsis <- function(X,w) {
  validate(X,w); w<-w/sum(w)
  # Fixed ideal 1 and anti-ideal 0 retain score meaning under cohort changes.
  Z<-sweep(X,2,w,'*'); hi<-sqrt(rowSums(sweep(Z,2,w,'-')^2));lo<-sqrt(rowSums(Z^2))
  ifelse(hi+lo==0,.5,lo/(hi+lo))
}
ahp <- function(A) {
  stopifnot(nrow(A)==ncol(A),all(is.finite(A)),all(A>0),max(abs(A*t(A)-1))<1e-8)
  n<-nrow(A);stopifnot(n<=15)
  w<-exp(rowMeans(log(A)));w<-w/sum(w)
  lambda<-mean(as.vector(A%*%w)/w);ci<-if(n>1)(lambda-n)/(n-1) else 0
  ri<-c(0,0,.58,.90,1.12,1.24,1.32,1.41,1.45,1.49,1.51,1.48,1.56,1.57,1.59)[n]
  cr<-if(ri==0)0 else ci/ri; if(cr>.1)stop('AHP consistency ratio exceeds .1')
  list(weights=w,CR=cr)
}
rank_score <- function(v) rank(-v,ties.method='average')
safe_cor <- function(a,b) if(length(a)<3 || sd(a)==0 || sd(b)==0) NA_real_ else cor(a,b,method='spearman')

# Versioned identity streams: each semantic key owns a L'Ecuyer stream. No
# dependency on matrix size/order or the caller's RNG state. Length-prefixing
# prevents ambiguous concatenations. Six modular lanes initialize the native
# R generator (not a cryptographic hash); draw index is position in the stream.
keyed_uniform <- function(n,version,seed,scenario,family,project,criterion) {
  parts<-enc2utf8(as.character(c(version,seed,scenario,family,project,criterion)))
  key<-paste0(nchar(parts,type='bytes'),':',parts,collapse='|')
  bytes<-as.integer(charToRaw(key))
  lanes<-vapply(seq_len(6),function(lane) {
    h<-as.double(lane*104729)
    for(b in bytes)h<-(h*(131+lane*2)+b+1)%%2147483562
    as.integer(h+1)
  },integer(1))
  oldkind<-RNGkind();had<-exists('.Random.seed',envir=.GlobalEnv,inherits=FALSE)
  if(had)oldseed<-get('.Random.seed',envir=.GlobalEnv)
  on.exit({do.call(RNGkind,as.list(oldkind));if(had)assign('.Random.seed',oldseed,envir=.GlobalEnv)
           else if(exists('.Random.seed',envir=.GlobalEnv,inherits=FALSE))rm('.Random.seed',envir=.GlobalEnv)})
  RNGkind("L'Ecuyer-CMRG",'Inversion','Rejection')
  assign('.Random.seed',c(10407L,lanes),envir=.GlobalEnv)
  runif(n)
}

keyed_inputs <- function(ids,codes,w,reps,version,seed,scenario,concentration) {
  U<-array(NA_real_,c(length(ids),length(codes),reps))
  G<-matrix(NA_real_,length(codes),reps)
  for(j in seq_along(codes)) {
    G[j,]<-if(w[j]==0)rep(0,reps) else qgamma(keyed_uniform(reps,version,seed,scenario,'WEIGHTS','',codes[j]),
                 shape=pmax(w[j]*concentration,1e-9))
    for(i in seq_along(ids))U[i,j,]<-keyed_uniform(reps,version,seed,scenario,'SOURCE_ROUNDING',ids[i],codes[j])
  }
  list(rounding=U,weights=sweep(G,2,colSums(G),'/'))
}


budget_weights <- function(wt,groups,totals) {
  stopifnot(length(wt)==length(groups),length(wt)==length(totals))
  for(g in unique(groups)) {
    idx<-which(groups==g);target<-unique(totals[idx]);stopifnot(length(target)==1,target>=0)
    if(target==0)wt[idx]<-0 else {stopifnot(sum(wt[idx])>0);wt[idx]<-wt[idx]/sum(wt[idx])*target}
  }
  stopifnot(abs(sum(wt)-1)<1e-12);wt
}
