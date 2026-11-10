"""Review a completed dual-track coverage cycle without copying historical data."""
import argparse
import json
from pathlib import Path
from au_ree_v2.iteration_review import review_coverage_cycle
from au_ree_v2.review_storage import write_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--previous-review',help='Previous full review or delta index; omit only for a new compressed anchor')
    args = parser.parse_args()
    result = review_coverage_cycle(args.before, args.after, args.manifest)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_review(result,output,args.previous_review)
    print(json.dumps(result['stopping_rule'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
