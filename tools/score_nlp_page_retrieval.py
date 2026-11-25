"""Score paired frozen rankings against blinded, non-exhaustive physical-page references."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

ARMS = ('rules', 'rules_nlp')


def read(path):
    return json.loads(path.read_bytes())


def rate(hits, total):
    return {'hits': hits, 'n': total, 'rate': hits / total if total else None}


def summary(rows):
    eligible = [r for r in rows if r['reference_in_frame']]
    sufficient = [r for r in rows if r['sufficient_in_frame']]
    def paired(row):
        return ('both' if row['rules_hit5'] else 'nlp_only') if row['rules_nlp_hit5'] else ('rules_only' if row['rules_hit5'] else 'neither')
    result = {'n':len(rows), 'unjudged':sum(not r['reference_known'] for r in rows),
              'references_outside_pool':sum(r['reference_known'] and not r['reference_in_frame'] for r in rows),
              'paired_hit5':dict(Counter(map(paired,eligible)))}
    for arm in ARMS:
        result[arm] = {'hit1':rate(sum(r[arm+'_hit1'] for r in eligible),len(eligible)),
                       'hit5':rate(sum(r[arm+'_hit5'] for r in eligible),len(eligible)),
                       'known_hits_over_all_targets':rate(sum(r[arm+'_hit5'] for r in eligible),len(rows)),
                       'sufficient_hit5':rate(sum(r[arm+'_sufficient_hit5'] for r in sufficient),len(sufficient)),
                       'empty_queues':sum(not r[arm+'_pages'] for r in rows),
                       'page_slots':sum(r[arm+'_pages'] for r in rows)}
    return result


def score(predictions, split, references):
    frame = {d['sha256']:d['pages'] for d in split['documents'] if d['split']=='holdout'}
    cells = {(r['project_id'],r['column']):r for r in references}
    target = [(c['project_id'],col) for c in predictions['cases'] for col in c['columns']]
    if len(set(target))!=len(target) or len(cells)!=len(references) or set(target)!=set(cells):
        raise ValueError('Reference and target cell keys must coincide exactly')
    query_rows,cell_rows=[],[]
    def metrics(case, cols):
        annotations=[cells[case['project_id'],col] for col in cols]
        refs={(p['sha256'],p['page']) for r in annotations for p in r['pages']}
        positive={(p['sha256'],p['page']) for r in annotations if r['judgment']=='SUFFICIENT_TO_FILL' for p in r['pages']}
        for r in annotations:
            if bool(r['pages']) != (r['judgment']!='UNJUDGED'):
                raise ValueError('Unknown status and reference pages disagree')
        valid={p for p in refs if p[0] in frame and 1<=p[1]<=frame[p[0]]}
        pos=positive & valid
        row={'case_id':case['case_id'], 'project_id':case['project_id'],'field':case['field'],
             'columns':'|'.join(cols),'reference_known':bool(refs),'reference_in_frame':bool(valid),
             'sufficient_in_frame':bool(pos),'reference_page_count':len(refs),'pool_reference_page_count':len(valid)}
        for arm in ARMS:
            queue=list(map(tuple,case[arm]))
            if len(queue)>predictions['k'] or len(queue)!=len(set(queue)) or any(p[0] not in frame or not 1<=p[1]<=frame[p[0]] for p in queue):
                raise ValueError('Out-of-pool page, duplicated page or excessive review budget')
            row.update({arm+'_pages':len(queue),arm+'_hit1':bool(valid.intersection(queue[:1])),
                        arm+'_hit5':bool(valid.intersection(queue)), arm+'_sufficient_hit5':bool(pos.intersection(queue))})
        return row
    for c in predictions['cases']:
        query_rows.append(metrics(c,c['columns']))
        cell_rows.extend(metrics(c,[col]) for col in c['columns'])
    return ({'query':summary(query_rows),'cell':summary(cell_rows),
             'query_by_field':{f:summary([r for r in query_rows if r['field']==f]) for f in sorted({r['field'] for r in query_rows})},
             'cell_by_field':{f:summary([r for r in cell_rows if r['field']==f]) for f in sorted({r['field'] for r in cell_rows})}},
            query_rows,cell_rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment',required=True,type=Path)
    parser.add_argument('--references',required=True,nargs='+',type=Path)
    args=parser.parse_args()
    refs=[c for p in args.references for c in read(p)['cells']]
    result,q,c=score(read(args.experiment/'predictions.json'),read(args.experiment/'split.json'),refs)
    (args.experiment/'retrieval_metrics.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    for name,rows in [('query_hits.csv',q),('cell_hits.csv',c)]:
        with (args.experiment/name).open('w',encoding='utf-8-sig',newline='') as f:
            wr=csv.DictWriter(f,fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)


if __name__=='__main__':
    main()
