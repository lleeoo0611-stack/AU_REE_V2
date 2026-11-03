"""Selective page extraction: native, positioned text, then explicit local OCR.

No glyph substitution or numerical correction is guessed. Evidence consumers
must still validate source scope, units, dates and rendered page values.
"""
import re
import json
from datetime import datetime,timezone
from pathlib import Path
from pypdf import PdfReader
from .store import filehash,canonical


def readable(text):
    chars=[c for c in text if not c.isspace()]
    return bool(chars) and sum(32<=ord(c)<127 for c in chars)/len(chars)>.88


def extract_page(path, number, tessdata=None, markers=()):
    import pymupdf
    path=Path(path)
    with pymupdf.open(path) as doc:
        if not 1<=number<=len(doc):raise ValueError('Physical page out of range')
        page=doc[number-1]
        native_error=None
        try:native=PdfReader(path).pages[number-1].extract_text() or ''
        except Exception as exc:native='';native_error=type(exc).__name__
        alternate=page.get_text(sort=True)
        good=lambda t:readable(t) and all(m in re.sub(r'\s+',' ',t) for m in markers)
        method='PYPDF_NATIVE';text=native
        if not good(text):method='MUPDF_POSITIONED';text=alternate
        model_sha=None
        if not good(text) and tessdata:
            model=Path(tessdata)/'eng.traineddata'
            model_sha=filehash(model)
            tp=page.get_textpage_ocr(language='eng',dpi=200,full=True,tessdata=str(Path(tessdata).resolve()))
            text=page.get_text(textpage=tp);method='MUPDF_TESSERACT_200DPI_SELECTED_PAGE'
        return {'source_sha256':filehash(path),'physical_page':number,'version':'pdf-page-v1',
                'method':method,'backend_version':pymupdf.VersionBind,'model_sha256':model_sha,
                'native_error':native_error,'native_text':native,'positioned_text':alternate,'text':text,
                'status':'EXTRACTED_REQUIRES_SCOPE_VALIDATION' if good(text) else 'UNREADABLE',
                'transformations':['NATIVE_AND_POSITIONED_TEXT_ATTEMPTED','NO_GUESSED_CHARACTER_OR_NUMERIC_SUBSTITUTION']}


def capture_pages(root, source, pages, tessdata=None):
    """One source manifest, content-addressed derivatives, per-page isolation."""
    import hashlib
    root=Path(root);path=root/'data/manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8'));outcomes=[]
    if filehash(root/source['path'])!=source['sha256']:raise ValueError('PDF source checksum mismatch')
    for page in sorted(set(pages)):
        try:
            result=extract_page(root/source['path'],page,tessdata)
            raw=(canonical(result)+'\n').encode();sha=hashlib.sha256(raw).hexdigest()
            target=root/'data/snapshots'/(sha+'.json')
            if not target.exists():target.write_bytes(raw)
            now=datetime.now(timezone.utc).isoformat();key=source['key']+'_page_'+str(page)
            entry=dict(key=key,kind='pdf_page_extraction',url=source['url'],source_sha256=source['sha256'],physical_page=page,sha256=sha,path=target.relative_to(root).as_posix(),acquired_at=now,available_date=now[:10])
            if source.get('publication_date'):entry['publication_date']=source['publication_date']
            if not any(s['key']==key and s['sha256']==sha for s in manifest['snapshots']):manifest['snapshots'].append(entry)
            outcomes.append(dict(page=page,status=result['status'],method=result['method'],sha256=sha))
        except Exception as exc:outcomes.append(dict(page=page,status='UNAVAILABLE',reason=type(exc).__name__))
    path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return outcomes
