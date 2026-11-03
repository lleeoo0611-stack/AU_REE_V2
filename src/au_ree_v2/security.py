"""Publication guard for literal and repeatedly encoded credential query parameters."""
import html,re
from urllib.parse import unquote
PATTERN=re.compile(r'[?&]\s*(?:access[_\s-]*token|api[_\s-]*key|token|signature|sig)\s*=',re.I)
def sensitive_reference(text):
    for _ in range(8):text=html.unescape(unquote(text))
    return bool(PATTERN.search(text))


_REDACT=re.compile(r'''(?:[?&]|&amp;|\\u0026)\s*(?:access[_\s-]*token|api[_\s-]*key|token|signature|sig)\s*=\s*[^\s"'<>\\&]*''',re.I)

def redact_reference_text(text):
    """Remove the parameter AND value; never return or log the credential value."""
    result,count=_REDACT.subn('?redacted_reference=REMOVED',text)
    if sensitive_reference(result):raise ValueError('Unsupported encoded credential reference; retain original privately')
    return result,count


def public_snapshot(root,raw,suffix):
    """Keep original bytes locally; publish only a declared, hash-bound derivative."""
    from pathlib import Path
    import hashlib
    text=raw.decode('utf-8',errors='backslashreplace')
    if not sensitive_reference(text):return raw,{}
    sha=hashlib.sha256(raw).hexdigest();private=Path(root)/'work/retained_originals'/(sha+suffix)
    private.parent.mkdir(parents=True,exist_ok=True)
    if not private.exists():private.write_bytes(raw)
    if raw.startswith((b'%PDF',b'PK\x03\x04')):
        raise ValueError('Binary document requires a separate redacted derivative; original retained privately')
    safe,count=redact_reference_text(text)
    return safe.encode('utf-8'),{'unpublished_original_sha256':sha,'publication_derivative':True,
        'redacted_query_parameters':count,'publication_transform':'CREDENTIAL_QUERY_PARAMETERS_REMOVED_V1',
        'original_retention':'LOCAL_IGNORED_WORK_RETAINED_ORIGINALS_NOT_INCLUDED_IN_PUBLIC_REPLAY'}


def public_export(value):
    """Scientific values/IDs stay intact; historical private URL references are scrubbed."""
    if isinstance(value,dict):return {k:public_export(v) for k,v in value.items()}
    if isinstance(value,list):return [public_export(v) for v in value]
    if isinstance(value,str) and sensitive_reference(value):return redact_reference_text(value)[0]
    return value
