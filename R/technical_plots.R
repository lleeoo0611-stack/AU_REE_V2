# Redraw source-bound case figures from the CLI's editable CSVs; no MCDA scores.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==1)
folder <- args[1]
cells <- read.csv(file.path(folder,"technical_cells.csv"),stringsAsFactors=FALSE,check.names=FALSE)
flot <- read.csv(file.path(folder,"technical_grade_recovery.csv"),stringsAsFactors=FALSE)
derived <- read.csv(file.path(folder,"technical_derived.csv"),stringsAsFactors=FALSE)
if(nrow(flot)>0) {
  svg(file.path(folder,"technical_grade_recovery.svg"),width=9,height=6)
  stages <- unique(flot$product); cols <- seq_along(stages)
  plot(flot$recovery_pct,flot$grade_pct,pch=19,col=cols[match(flot$product,stages)],
       xlab="TREO recovery (%; conditional same-feed basis)",ylab="TREO grade (%)",
       main="Selected composite: grade-recovery trade-off",sub="Different product stages; measurement uncertainty not quantified")
  text(flot$recovery_pct,flot$grade_pct,flot$test_id,pos=3,cex=.8)
  legend("topright",stages,col=cols,pch=19,bty="n",cex=.75); dev.off()
}
r <- derived[derived$variable=="reagent_intensity_kg_t_dry_feed",]
if(nrow(r)>0) {
 svg(file.path(folder,"technical_reagent_intensity.svg"),width=10,height=8)
 par(mar=c(12,4,3,1))
 barplot(r$value,names.arg=paste(r$stage,r$reagent,sep=" / "),las=2,cex.names=.85,
         ylab="kg formulation / t dry plant feed",main="Scoping design reagent intensity")
 mtext("Annual feed denominator; active chemical purity not established",side=3,cex=.8);dev.off()
}
x <- cells[cells$quantity=="extraction_pct",]
if(nrow(x)>0) {
 svg(file.path(folder,"technical_element_matrix.svg"),width=11,height=9)
 samples <- unique(x$sample_id);par(mfrow=c(length(samples),1),mar=c(4,5,3,2))
 for(s in samples) {
  z <- x[x$sample_id==s,]; els <- unique(z$basis); m <- matrix(NA,nrow=length(els),ncol=max(z$source_column,na.rm=TRUE))
  for(i in seq_len(nrow(z))) m[match(z$basis[i],els),z$source_column[i]] <- z$value[i]
  image(seq_len(ncol(m)),seq_len(nrow(m)),t(m),xlab="Original printed column position (not replicate)",ylab="Element",yaxt="n",
        main=paste(s,"- printed values, including source anomaly"),col=hcl.colors(100,"YlOrRd",rev=TRUE),zlim=range(x$value,na.rm=TRUE))
  axis(2,seq_along(els),els,las=2);box()
 }
 dev.off()
}

# Same two source-qualified design cases: performance is separate from evidence maturity.
process_file<-file.path(folder,'technical_process_concentrate_fixed','matrix.csv')
if(file.exists(process_file)) {
  z<-read.csv(process_file)
  if(nrow(z)>=2) {
    svg(file.path(folder,'technical_process_concentrate.svg'),width=8,height=5)
    plot(100*z$TPR,100*z$TPG,pch=19,col='#176b72',xlim=range(100*z$TPR)+c(-1,1),
      ylim=range(100*z$TPG)+c(-1,1),xlab='Whole-ore TREO recovery to mineral concentrate (%)',
      ylab='Mineral concentrate TREO grade (%)',main='Named engineering design demonstration (n = 2)')
    text(100*z$TPR,100*z$TPG,labels=z$case_id,pos=3,cex=.75)
    mtext('No operating outcome, measurement-error bounds or national ranking inferred',side=1,line=4,cex=.7)
    dev.off()
  }
}
