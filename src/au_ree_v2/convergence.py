"""Opt-in convergence with an evidenced, separately retained acquisition backlog."""
POLICY = 'CONSECUTIVE_ZERO_GAIN_WITH_BLOCKED_BACKLOG'
FAILURE_TYPES = {'HTTP_403', 'ACCESS_RESTRICTED', 'NO_SAME_EDITION_COPY',
                 'BOUNDED_TIMEOUT', 'NETWORK_ERROR'}


def blocked_backlog(manifest, columns, projects):
    blocked = manifest.get('blocked_acquisitions')
    actions = manifest.get('unresolved_acquisition_actions')
    problems = []
    if not isinstance(blocked, list) or not isinstance(actions, list):
        return [], ['acquisition:blocked_backlog_undeclared']
    ids = []
    number = manifest.get('round_number')
    for entry in blocked:
        if not isinstance(entry, dict):
            problems.append('acquisition:invalid_blocked_entry')
            continue
        ids.append(entry.get('action_id'))
        first = entry.get('first_blocked_round')
        pids, fields = entry.get('project_ids'), entry.get('columns')
        if (not isinstance(entry.get('action_id'), str) or not entry['action_id'].strip()
            or not (str(entry.get('url', '')).strip() or str(entry.get('work_id', '')).strip())
            or entry.get('failure_type') not in FAILURE_TYPES
            or type(first) is not int or type(number) is not int or not 1 <= first <= number
            or not isinstance(pids, list) or not pids or not set(pids) <= set(projects)
            or not isinstance(fields, list) or not fields or not set(fields) <= set(columns)
            or not str(entry.get('manual_route', '')).strip()
            or not str(entry.get('impact_scope', '')).strip()
            or not isinstance(entry.get('evidence_refs'), list) or not entry['evidence_refs']
            or any(not isinstance(r,str) or not r.strip() for r in entry['evidence_refs'])):
            problems.append('acquisition:invalid_blocked_entry')
    if (any(not isinstance(x,str) for x in ids+actions) or len(set(ids)) != len(ids)
        or len(set(actions)) != len(actions) or set(ids) != set(actions)):
        problems.append('acquisition:unclassified_unresolved_actions')
    # Do not grant exceptions for even one invalid declaration.
    return ([] if problems else blocked), sorted(set(problems))


def consecutive_rule(manifest, gain, eligible, baseline_sha):
    """Recount consecutive prior receipts; never trust a supplied running counter.

    Prior receipts are reviewer evidence, just like source/test declarations.
    Require chronological, hash-linked exports and the same opt-in policy.
    A failed/incomplete receipt or gain resets the streak; malformed chains fail.
    """
    required = manifest.get('consecutive_zero_rounds', 2)
    number = manifest.get('round_number')
    history = manifest.get('previous_cycle_reviews', [])
    if type(required) is not int or required < 1:
        raise ValueError('CYCLE_INVALID_CONSECUTIVE_ZERO_ROUNDS')
    problems=[]
    if type(number) is not int or number < 1 or not isinstance(history,list):
        return dict(required_zero_rounds=required, consecutive_zero_rounds=0), ['convergence:invalid_history']
    count=0
    previous=None
    seen=set()
    for receipt in history:
        if not isinstance(receipt,dict):
            problems.append('convergence:invalid_history'); break
        n=receipt.get('round_number'); rule=receipt.get('stopping_rule',{})
        if (type(n) is not int or n < 1 or n >= number or n in seen
            or rule.get('policy') != POLICY
            or (previous is not None and (n != previous['round_number']+1
                or receipt.get('baseline_csv_sha256') != previous.get('current_csv_sha256')))
            or not receipt.get('baseline_csv_sha256') or not receipt.get('current_csv_sha256')
            or type(rule.get('newly_filled_cells')) is not int or rule['newly_filled_cells'] < 0
            or type(rule.get('eligible')) is not bool or not isinstance(rule.get('incomplete'),list)):
            problems.append('convergence:invalid_history'); break
        seen.add(n)
        count = count+1 if rule['eligible'] and not rule['incomplete'] and rule['newly_filled_cells']==0 else 0
        previous=receipt
    if previous is not None and (previous['round_number'] != number-1
            or previous['current_csv_sha256'] != baseline_sha):
        problems.append('convergence:unlinked_history')
    count = count+1 if eligible and not problems and gain==0 else 0
    return dict(required_zero_rounds=required,consecutive_zero_rounds=count), sorted(set(problems))
