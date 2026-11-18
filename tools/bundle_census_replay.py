"""Package already acquired bytes for local, cross-checkout Census replay."""
import argparse
import json
import re
import shutil
from pathlib import Path

from au_ree_v2.store import canonical, filehash


def bundle(root, receipt_path, destination):
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    if (root/'results') in destination.parents or (root/'data') in destination.parents:
        raise ValueError('Replay originals belong in local work storage')
    receipt = json.loads(Path(receipt_path).read_text(encoding='utf8'))
    lock_path = root/'results/phase22-2026-11-06/snapshot_lock.json'
    frozen = json.loads(lock_path.read_text(encoding='utf8'))
    assets = {}
    for source in [*receipt['snapshots'], *frozen]:
        for item in (source, *source.get('original_responses', [])):
            sha = item['sha256']
            path = (root/item['path']).resolve(strict=True)
            if not re.fullmatch('[0-9a-f]{64}', sha) or filehash(path) != sha:
                raise ValueError(f'Source checksum mismatch for {source["key"]}')
            assets.setdefault(sha, path)
    library = destination/'assets'
    library.mkdir(parents=True)
    for sha, path in sorted(assets.items()):
        target = library/sha
        shutil.copyfile(path, target)
        if filehash(target) != sha:
            raise ValueError(f'Copied asset checksum mismatch: {sha}')
    # Asset fallback uses SHA, so the receipt keeps its original snapshot metadata.
    shutil.copyfile(receipt_path, destination/'source_acquisition.json')
    result = dict(receipt_sha256=filehash(receipt_path), lock_sha256=filehash(lock_path),
                  assets=len(assets), asset_bytes=sum(p.stat().st_size for p in assets.values()))
    (destination/'bundle_verification.json').write_text(canonical(result)+'\n', encoding='utf8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(canonical(bundle(args.root, args.receipt, args.out)))
