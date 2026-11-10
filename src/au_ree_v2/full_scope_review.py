"""Coverage gates for a single whole-cohort round, separate from legacy policies."""


def review_full_scope(old, new, columns, manifest, blocked_action_ids=()):
    """Return omissions; evidence references document review, not proof of semantics.

    Old blanks stay in scope even if filled. Newly admitted projects bring their
    remaining blanks into this same round. Batches cannot each declare STOP.
    """
    scope = manifest.get('full_scope', {})
    problems = []
    baseline = scope.get('baseline_project_ids', [])
    if not isinstance(baseline, list) or len(set(baseline)) != len(baseline) or set(baseline) != set(old):
        problems.append('full_scope:baseline_projects')
    expected_cells = {(pid, c) for pid, row in old.items() for c in columns if not row[c]}
    expected_cells |= {(pid, c) for pid in set(new)-set(old) for c in columns if not new[pid][c]}

    def check_records(name, expected, keys):
        records = scope.get(name)
        if not isinstance(records, list):
            problems.append('full_scope:'+name+':undeclared')
            return
        if any(not isinstance(r, dict) or any(k not in r for k in keys) for r in records):
            problems.append('full_scope:'+name+':invalid')
            return
        identities = [tuple(r[k] for k in keys) for r in records]
        if len(set(identities)) != len(identities) or set(identities) != expected:
            problems.append('full_scope:'+name+':coverage')
        for r in records:
            if (r.get('completed') is not True or not str(r.get('disposition', '')).strip()
                    or not isinstance(r.get('query_ids'), list) or not r['query_ids']
                    or not isinstance(r.get('source_review_ids'), list) or not r['source_review_ids']):
                problems.append('full_scope:'+name+':unfinished')
                break

    check_records('cell_reviews', expected_cells, ('project_id', 'column'))
    check_records('project_reviews', {(p,) for p in set(old)|set(new)}, ('project_id',))
    for name in ('candidate', 'external_lead'):
        expected = scope.get('expected_'+name+'_ids')
        if not isinstance(expected, list) or len(set(expected)) != len(expected):
            problems.append('full_scope:'+name+':baseline_undeclared')
            continue
        check_records(name+'_reviews', {(x,) for x in expected}, ('lead_id',))
    actions = scope.get('source_actions')
    if not isinstance(actions, list) or not actions:
        problems.append('full_scope:source_actions:undeclared')
    else:
        ids = [a.get('action_id') for a in actions if isinstance(a, dict)]
        if len(ids) != len(actions) or None in ids or len(set(ids)) != len(ids):
            problems.append('full_scope:source_actions:invalid')
        if any(not isinstance(a, dict) or (a.get('completed') is not True and a.get('action_id') not in blocked_action_ids)
               or not str(a.get('evidence', '')).strip() for a in actions):
            problems.append('full_scope:source_actions:unfinished')
        if not set(blocked_action_ids) <= set(ids):
            problems.append('full_scope:blocked_action_missing')
    return sorted(set(problems))
