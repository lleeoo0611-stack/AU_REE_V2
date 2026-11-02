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
