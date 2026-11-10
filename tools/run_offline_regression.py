"""Run all branch tests against read-only local fixtures and a writable overlay.

No downloads: Python socket connections/DNS are denied in this process and its
Python children. Original tests and production code are not patched or skipped.
Byte-identical test copies run in the overlay so even import-time fixture reads
resolve locally; current production code is imported from this checkout.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture-root',type=Path,required=True)
    parser.add_argument('--overlay',type=Path,required=True)
    parser.add_argument('--junitxml',required=True)
    args=parser.parse_args()
    fixture=args.fixture_root.resolve();overlay=args.overlay.resolve()
    if overlay.is_relative_to(fixture):raise ValueError('OVERLAY_MUST_BE_OUTSIDE_FIXTURE_ROOT')
    overlay.mkdir(parents=True,exist_ok=True);(overlay/'work').mkdir(exist_ok=True)
    for name in ('config','R','tools','docs','src','tests'):
        shutil.copytree(ROOT/name,overlay/name,dirs_exist_ok=True)
    links=[(overlay/'data',fixture/'data')]
    (overlay/'results').mkdir(exist_ok=True)
    # Prefer this branch's reports; other historical phases come from fixtures.
    for name in sorted({p.name for parent in (ROOT/'results',fixture/'results') for p in parent.iterdir() if p.is_dir()}):
        target=ROOT/'results'/name
        if not target.is_dir():target=fixture/'results'/name
        links.append((overlay/'results'/name,target))
    for link,target in links:
        if not link.exists():
            command="New-Item -ItemType Junction -Path '"+str(link).replace("'","''")+"' -Target '"+str(target).replace("'","''")+"' | Out-Null"
            subprocess.run(['powershell','-NoProfile','-Command',command],check=True)
        if link.resolve()!=target.resolve():raise ValueError('UNEXPECTED_FIXTURE_JUNCTION')
    # Also protect Python subprocesses invoked by existing integration tests.
    guard=overlay/'offline-guard';guard.mkdir(exist_ok=True)
    code='''import os,sys
from pathlib import Path
protected_root=Path(os.environ['AU_REE_READ_ONLY_FIXTURES']).resolve()
def guard(event,args):
    if event in {'socket.connect','socket.getaddrinfo'}:
        raise PermissionError('Offline regression forbids network access')
    def protected(p):
        return isinstance(p,(str,bytes,os.PathLike)) and Path(os.fsdecode(p)).resolve().is_relative_to(protected_root)
    if event=='open':
        p,mode,flags=args
        if ((mode and any(c in mode for c in 'wax+')) or (flags and flags & (os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_CREAT|os.O_TRUNC))) and protected(p):
            raise PermissionError('Read-only historical fixture: '+str(p))
    if event in {'os.remove','os.rmdir','os.mkdir','os.chmod','os.utime','os.truncate'} and protected(args[0]):
        raise PermissionError('Read-only fixture mutation')
    if event in {'os.rename','os.link','os.symlink'} and any(protected(p) for p in args[:2]):
        raise PermissionError('Read-only fixture mutation')
    if event in {'shutil.copyfile','shutil.copymode','shutil.copystat','shutil.copytree'} and protected(args[1]):
        raise PermissionError('Read-only fixture destination')
sys.addaudithook(guard)
'''
    (guard/'sitecustomize.py').write_text(code,encoding='utf8')
    # Some legacy tests intentionally replace PYTHONPATH with ROOT/src.
    (overlay/'src/sitecustomize.py').write_text(code,encoding='utf8')
    os.environ['AU_REE_READ_ONLY_FIXTURES']=str(fixture)
    os.environ['PYTHONPATH']=os.pathsep.join((str(guard),str(ROOT/'src'),str(ROOT)))
    exec(compile(code,str(guard/'sitecustomize.py'),'exec'),{})
    sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
    import pytest
    import hashlib
    for source in (ROOT/'tests').glob('*.py'):
        if source.read_bytes()!=(overlay/'tests'/source.name).read_bytes():raise ValueError('TEST_COPY_CHANGED')
    print('All tests; production source:',ROOT/'src')
    print('Read-only fixtures:',fixture,'; overlay:',overlay)
    print('Python network/DNS denied; no skips added')
    return pytest.main(['-q','-p','no:cacheprovider',str(overlay/'tests'),'--junitxml='+str(Path(args.junitxml).resolve())])


if __name__=='__main__':raise SystemExit(main())
