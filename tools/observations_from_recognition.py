"""Export typed raw review candidates from a cached document recognition report."""

import argparse
import json
from pathlib import Path

from au_ree_v2.nlp import automatic_observations
from au_ree_v2.observation_schema import payload
from au_ree_v2.store import canonical


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_bytes())
    records = [payload(observation) for observation in automatic_observations(report)]
    with args.out.open("x", encoding="utf-8", newline="\n") as output:
        for observation in records:
            output.write(canonical(observation) + "\n")


if __name__ == "__main__":
    main()
