"""Review a completed dual-track coverage cycle without copying historical data."""
import argparse
import json
from pathlib import Path
from au_ree_v2.iteration_review import review_coverage_cycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = review_coverage_cycle(args.before, args.after, args.manifest)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    print(json.dumps(result['stopping_rule'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
