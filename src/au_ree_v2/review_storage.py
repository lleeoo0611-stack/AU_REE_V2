"""Lossless hash-checked JSON difference chains and deterministic gzip snapshots.

Historical full JSON files remain readable and are never rewritten implicitly.
Every new index contains only a delta (or an initial compressed anchor reference).
"""
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path

FORMAT='coverage-review-delta-v1'


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf8')


def sha(raw):return hashlib.sha256(raw).hexdigest()


def same(a,b):
    """JSON byte semantics include object order and numeric/bool token types."""
    if type(a) is not type(b):return False
    if isinstance(a,dict):return list(a)==list(b) and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b


def identity_fields(items):
    if not items or any(not isinstance(v,dict) for v in items):return None
    for keys in (('project_id','column'),('project_id',),('lead_id',),('action_id',)):
        if all(all(k in v and isinstance(v[k],str) for k in keys) for v in items):
            ids=[json.dumps([v[k] for k in keys],ensure_ascii=False,separators=(',',':')) for v in items]
            if len(set(ids))==len(ids):return keys
    return None


def delta(old,new):
    if same(old,new):return None
    if isinstance(old,dict) and isinstance(new,dict):
        changes={k:delta(old[k],v) if k in old else {'op':'replace','value':v}
                 for k,v in new.items() if k not in old or not same(old[k],v)}
        return dict(op='dict',changes=changes,remove=[k for k in old if k not in new],
                    **({'order':list(new)} if list(new)!=[k for k in old if k in new]+[k for k in new if k not in old] else {}))
    if isinstance(old,list) and isinstance(new,list):
        keys=identity_fields(old+new)
        # Repeated identities across old/new are expected; uniqueness is per side.
        if keys is None:
            keys=identity_fields(old)
            if keys!=identity_fields(new):keys=None
        if keys:
            key=lambda v:json.dumps([v[k] for k in keys],ensure_ascii=False,separators=(',',':'))
            a,b={key(v):v for v in old},{key(v):v for v in new}
            if len(a)==len(old) and len(b)==len(new):
                patch=delta(a,b)
                return dict(op='keyed_list',keys=list(keys),patch=patch)
        return dict(op='list',length=len(new),changes={str(i):delta(old[i],v) if i<len(old)
                    else {'op':'replace','value':v} for i,v in enumerate(new)
                    if i>=len(old) or not same(old[i],v)})
    return dict(op='replace',value=new)


def apply_delta(old,patch):
    if patch is None:return copy.deepcopy(old)
    op=patch['op']
    if op=='replace':return copy.deepcopy(patch['value'])
    if op=='dict':
        result=copy.deepcopy(old)
        for key in patch['remove']:del result[key]
        for key,change in patch['changes'].items():result[key]=apply_delta(result.get(key),change)
        if 'order' in patch:
            if set(patch['order'])!=set(result) or len(patch['order'])!=len(result):raise ValueError('REVIEW_DELTA_BAD_ORDER')
            result={k:result[k] for k in patch['order']}
        return result
    if op=='keyed_list':
        keys=patch['keys']
        a={json.dumps([v[k] for k in keys],ensure_ascii=False,separators=(',',':')):v for v in old}
        return list(apply_delta(a,patch['patch']).values())
    if op=='list':
        result=copy.deepcopy(old[:patch['length']])
        result.extend([None]*(patch['length']-len(result)))
        for index,change in patch['changes'].items():result[int(index)]=apply_delta(result[int(index)],change)
        return result
    raise ValueError('REVIEW_DELTA_UNKNOWN_OPERATION')


def restore_review(path,_seen=None,verify_snapshot=True):
    """Return exact UTF-8 full report bytes, validating every link and snapshot."""
    path=Path(path).resolve();seen=set() if _seen is None else _seen
    if path in seen or len(seen)>=512:raise ValueError('REVIEW_DELTA_CYCLIC_OR_TOO_DEEP')
    seen.add(path)
    raw=path.read_bytes();index=json.loads(raw)
    if index.get('format')!=FORMAT:return raw
    base=index.get('base')
    if base is None:
        restored=gzip.decompress((path.parent/index['full_gzip']).read_bytes())
    else:
        prior=path.parent/base['path']
        if sha(prior.read_bytes())!=base['index_sha256']:raise ValueError('REVIEW_DELTA_BASE_INDEX_HASH')
        old=restore_review(prior,seen,verify_snapshot)
        if sha(old)!=base['full_sha256']:raise ValueError('REVIEW_DELTA_BASE_FULL_HASH')
        restored=encoded(apply_delta(json.loads(old),index['delta']))
        if index.get('serialization')=='UTF8_INDENT2_CRLF':restored=restored.replace(b'\n',b'\r\n')
    if sha(restored)!=index['full_sha256']:raise ValueError('REVIEW_DELTA_RESTORED_HASH')
    snapshot=path.parent/index['full_gzip']
    if verify_snapshot and gzip.decompress(snapshot.read_bytes())!=restored:
        raise ValueError('REVIEW_DELTA_SNAPSHOT_MISMATCH')
    return restored


def write_review(report,path,previous=None,original_bytes=None):
    path=Path(path).resolve()
    if path.exists():raise ValueError('REVIEW_STORAGE_REFUSES_OVERWRITE')
    if previous and Path(previous).resolve()==path:raise ValueError('REVIEW_DELTA_SELF_REFERENCE')
    raw=encoded(report);serialization='UTF8_INDENT2_LF'
    if original_bytes is not None:
        if original_bytes==raw.replace(b'\n',b'\r\n'):serialization='UTF8_INDENT2_CRLF'
        elif original_bytes!=raw:raise ValueError('REVIEW_STORAGE_UNSUPPORTED_ORIGINAL_SERIALIZATION')
        raw=original_bytes
    path.parent.mkdir(parents=True,exist_ok=True)
    snapshot=path.with_name(path.stem+'.full.json.gz')
    if snapshot.exists():raise ValueError('REVIEW_STORAGE_REFUSES_OVERWRITE')
    index=dict(format=FORMAT,full_sha256=sha(raw),full_gzip=snapshot.name,serialization=serialization,base=None,delta=None)
    if previous:
        previous=Path(previous).resolve();old=restore_review(previous)
        index.update(base=dict(path=Path(os.path.relpath(previous,path.parent)).as_posix(),
                               index_sha256=sha(previous.read_bytes()),full_sha256=sha(old)),
                     delta=delta(json.loads(old),report))
    # The full report lives only in gzip; never leave a duplicate uncompressed file.
    snapshot.write_bytes(gzip.compress(raw,mtime=0))
    path.write_text(json.dumps(index,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8',newline='\n')
    if restore_review(path)!=raw:raise ValueError('REVIEW_STORAGE_ROUNDTRIP_FAILED')
    return dict(full_sha256=sha(raw),full_bytes=len(raw),index_bytes=path.stat().st_size,
                gzip_bytes=snapshot.stat().st_size,restored_byte_identical=True)
