"""Record the integration baseline, ancestry and protected overlap of remote tips."""

import json
from pathlib import Path
import subprocess

from au_ree_v2.derived_cache import atomic_json


BASELINE = 'dcda87e81e1250d443f73c1984faaa7beaa19930'
PROTECTED = ('src/', 'R/', 'data/', 'config/', 'results/')


def _git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def _changes(root, before, after):
    return set(_git(root, 'diff', '--name-only', '--no-renames', '-z', before, after).split('\0')) - {''}


def _ancestor(root, before, after):
    result = subprocess.run(['git', 'merge-base', '--is-ancestor', before, after], cwd=root, check=False)
    if result.returncode not in (0, 1):
        raise ValueError('GIT_ANCESTRY_UNAVAILABLE')
    return result.returncode == 0


def associations(root, base, ref, head):
    result = {'ref': ref, 'commit': head}
    if _ancestor(root, head, base):
        return {**result, 'status': 'IN_BASELINE'}
    if _ancestor(root, base, head):
        return {**result, 'status': 'ALREADY_DESCENDS_FROM_BASELINE'}
    common = _git(root, 'merge-base', base, head)
    overlap = sorted(set.intersection(_changes(root, common, base), _changes(root, common, head)))
    protected = [name for name in overlap if name.startswith(PROTECTED)]
    return {**result, 'status': 'INTEGRATION_BLOCKED' if protected else 'DIVERGENT_NOT_INTEGRATED',
            'common_ancestor': common, 'protected_overlap': protected,
            'reason': ('COMMON_ANCESTOR_WITH_PROTECTED_EDITS_ON_BOTH_TIPS' if protected else
                       'DIVERGENT_TIP_WITHOUT_VALIDATED_EQUIVALENCE')}


def record(root, output, *, pulls=None, ci=None, baseline=BASELINE):
    refs = _git(root, 'for-each-ref', '--format=%(refname:short) %(objectname)', 'refs/remotes/origin').splitlines()
    branches = []
    for row in refs:
        ref, sha = row.split()
        if ref not in {'origin', 'origin/HEAD'}:
            branches.append(associations(root, baseline, ref, sha))
    pull_rows = [{'number': row['number'], 'url': row['html_url'], 'draft': row['draft'],
                  'head': row['head']['ref'], 'head_sha': row['head']['sha'], 'base': row['base']['ref']}
                 for row in (json.loads(Path(pulls).read_bytes()) if pulls else ())]
    checks = [{key: row[key] for key in ('id', 'name', 'head_sha', 'status', 'conclusion', 'html_url')}
              for row in (json.loads(Path(item).read_bytes()) for item in ci or ())]
    result = {'schema': 'phase10-repository-inventory-v1', 'integration_baseline': baseline,
              'baseline_branch': 'feat/disable-c1-and-resource-normalization-20261127',
              'baseline_pull_request': 27, 'remote_tips': branches, 'open_prs': pull_rows, 'baseline_ci': checks,
              'merged_new_tips': [], 'missing_remote_receipts': not (pulls and ci)}
    atomic_json(Path(output), result)
    return result
