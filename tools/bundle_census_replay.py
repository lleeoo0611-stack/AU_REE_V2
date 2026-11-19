"""Assemble a portable Census receipt and hash-addressed original files."""
import argparse
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from au_ree_v2.store import canonical, filehash


def bundle(root, receipt_path, destination, source_assets=None):
    root = Path(root).resolve()
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    if any(destination.is_relative_to(root / name) for name in ('data', 'results')):
        raise ValueError('Replay originals belong in local work storage')
    receipt = json.loads(Path(receipt_path).read_bytes())
    lock_path = root / 'results/phase22-2026-11-06/snapshot_lock.json'
    frozen = json.loads(lock_path.read_bytes())
    library = Path(source_assets).resolve(strict=True) if source_assets else None
    assets = {}
    bindings = []
    for collection, sources in [('receipt', receipt['snapshots']), ('frozen', frozen)]:
        for source in sources:
            for role, item in [('snapshot', source), *[('original_response', a) for a in source.get('original_responses', [])]]:
                sha = item['sha256']
                if not re.fullmatch('[0-9a-f]{64}', sha):
                    raise ValueError(f'Invalid checksum for {source["key"]}')
                if sha not in assets:
                    path = (library / sha if library else root / item['path']).resolve(strict=True)
                    if not path.is_relative_to(library or root) or filehash(path) != sha:
                        raise ValueError(f'Source checksum or path mismatch for {source["key"]}')
                    assets[sha] = path
                bindings.append(dict(collection=collection, key=source['key'], role=role,
                                     sha256=sha, parent_sha256=source['sha256'], kind=source.get('kind'),
                                     url=source.get('url'), acquisition_method=source.get('acquisition_method'),
                                     asset='assets/'+sha))
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name('.bundle-'+uuid4().hex)
    try:
        (staging/'assets').mkdir(parents=True)
        for sha, path in sorted(assets.items()):
            target = staging/'assets'/sha
            shutil.copyfile(path, target)
            if filehash(target) != sha:
                raise ValueError(f'Copied asset checksum mismatch: {sha}')
        shutil.copyfile(receipt_path, staging/'source_acquisition.json')
        manifest = staging/'asset_manifest.json'
        manifest.write_bytes((canonical(bindings)+'\n').encode())
        result = dict(receipt_sha256=filehash(receipt_path), lock_sha256=filehash(lock_path),
                      manifest_sha256=filehash(manifest), references=len(bindings), assets=len(assets),
                      asset_bytes=sum(p.stat().st_size for p in assets.values()))
        (staging/'bundle_verification.json').write_bytes((canonical(result)+'\n').encode())
        staging.rename(destination)
    finally:
        if staging.is_dir():
            shutil.rmtree(staging)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='.', type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--source-assets', help='Optional existing SHA-named library', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    print(canonical(bundle(args.root, args.receipt, args.out, args.source_assets)))
