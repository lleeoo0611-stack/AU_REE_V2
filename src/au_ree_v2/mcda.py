"""Scoring and interval ranking used by study and analysis panels."""

import math


def interval_mcda(matrix, weights, threshold=.2):
    """Outer score/rank bounds; unknown utilities are sets, not random draws.

    Uses the same fixed-anchor SAW, TOPSIS and linear PROMETHEE functions
    as R/methods.R. PROMETHEE bounds are conservative because opponents'
    score extrema need not be simultaneously attainable. Ties occupy all
    tied positions. Bounds also allow independent criterion values, so they
    remain outer bounds when source cases have unmodelled dependencies.
    """
    if not matrix or not weights or not math.isfinite(threshold) or threshold<=0:
        raise ValueError('Require alternatives and a positive threshold')
    if any(not math.isfinite(w) or w<0 for w in weights) or sum(weights)<=0:
        raise ValueError('Invalid weights')
    w=[v/sum(weights) for v in weights]
    for row in matrix:
        if len(row)!=len(w) or any(len(v)!=2 or not all(math.isfinite(x) for x in v)
                                   or not 0<=v[0]<=v[1]<=1 for v in row):
            raise ValueError('Require finite ordered utility bounds in [0,1]')
    def saw(x):return sum(a*b for a,b in zip(x,w))
    def topsis(x):
        lo=math.sqrt(sum((a*b)**2 for a,b in zip(x,w)))
        hi=math.sqrt(sum(((1-a)*b)**2 for a,b in zip(x,w)))
        return lo/(lo+hi)
    def preference(d):return max(-1.,min(1.,d/threshold))
    result={m:[] for m in ('SAW','TOPSIS','PROMETHEE_II')}
    for i,row in enumerate(matrix):
        lower=[v[0] for v in row];upper=[v[1] for v in row]
        result['SAW'].append((saw(lower),saw(upper)))
        result['TOPSIS'].append((topsis(lower),topsis(upper)))
        flow=[]
        for side in (0,1):
            flow.append(sum(sum(w[k]*preference(row[k][side]-other[k][1-side])
                                for k in range(len(w)))
                            for j,other in enumerate(matrix) if j!=i)/max(1,len(matrix)-1))
        result['PROMETHEE_II'].append(tuple(flow))
    return {method:[dict(score_lower=lo,score_upper=hi,
                         rank_best=1+sum(a>hi+1e-12 for j,(a,b) in enumerate(bounds) if j!=i),
                         rank_worst=len(matrix)-sum(b<lo-1e-12 for j,(a,b) in enumerate(bounds) if j!=i))
                    for i,(lo,hi) in enumerate(bounds)]
            for method,bounds in result.items()}


def score(value, criterion, alternative=False):
    low, high = criterion['low'], criterion['high']
    if not math.isfinite(value) or high <= low:
        raise ValueError('Invalid score value or anchors')
    if criterion['function']=='log1p' and not alternative:
        val = (math.log1p(max(low, min(value,high)))-math.log1p(low))/(math.log1p(high)-math.log1p(low))
    else:
        val = (value-low)/(high-low)
    val = max(0., min(1., val))
    return 1-val if criterion['direction']=='MIN' else val
