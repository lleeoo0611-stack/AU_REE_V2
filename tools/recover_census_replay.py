"""Recover the byte-pinned inputs for a portable Census replay."""

import argparse
from pathlib import Path

from au_ree_v2.source_recovery import recover_census_assets
from au_ree_v2.store import canonical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', type=Path)
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--library', action='append', default=[], type=Path,
                        help='A local asset directory, original file, or ZIP of SHA-named assets')
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--request-budget', default=80, type=int)
    parser.add_argument('--timeout', default=12, type=int)
    args = parser.parse_args()
    result = recover_census_assets(args.root, args.release, args.out, libraries=args.library,
                                   online=args.online, request_budget=args.request_budget, timeout=args.timeout)
    print(canonical({key: value for key, value in result.items() if key != 'receipts'}))


if __name__ == '__main__':
    main()
