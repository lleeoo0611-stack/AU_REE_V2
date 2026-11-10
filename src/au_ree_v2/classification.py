"""Exact text-to-code projection, gated by explicit researcher approval."""
import json
from collections import Counter
from datetime import date
from pathlib import Path
from .store import canonical, filehash

FIELDS={'deposit_type':('礦床型態',{'code':'礦床型態代碼'}),
        'development_stage':('開發階段',{'code':'開發階段代碼','category':'開發階段類別'})}


def load_codebook(path):
    path=Path(path)
    cfg=json.loads(path.read_text(encoding='utf-8-sig'))
    if cfg.get('status') not in ('DRAFT','APPROVED') or not str(cfg.get('version','')).strip():
        raise ValueError('CODEBOOK_STATUS_OR_VERSION')
    if cfg['status']=='APPROVED':
        if not str(cfg.get('approved_by') or '').strip():raise ValueError('CODEBOOK_APPROVER_REQUIRED')
        try:date.fromisoformat(cfg['approved_date'])
        except (KeyError,TypeError,ValueError):raise ValueError('CODEBOOK_APPROVAL_DATE_REQUIRED') from None
    for group,(_,targets) in FIELDS.items():
        if not isinstance(cfg.get(group),dict):raise ValueError('CODEBOOK_MAPPING_REQUIRED')
        for text,entry in cfg[group].items():
            if not isinstance(entry,dict) or entry.get('status') not in ('MAPPED','UNMAPPED'):
                raise ValueError('CODEBOOK_ENTRY_STATUS')
            if entry['status']=='MAPPED' and any(not isinstance(entry.get(k),str) or not entry[k].strip() or entry[k]=='UNMAPPED' for k in targets):
                raise ValueError('CODEBOOK_MAPPED_VALUE_REQUIRED')
    return dict(config=cfg,sha256=filehash(path))


def classification_fills(row,provenance,book):
    """Return new cells only; exact dated text stays intact, no implicit synonyms."""
    cfg=book['config']
    if cfg['status']!='APPROVED':return []
    fills=[]
    for group,(source,targets) in FIELDS.items():
        text=row.get(source,'');entry=cfg[group].get(text,{})
        if not text or entry.get('status')!='MAPPED':continue
        native=next((p for p in provenance if p['project_id']==row['專案ID'] and p['column']==source),None)
        if native is None:raise ValueError('CODEBOOK_SOURCE_PROVENANCE_REQUIRED')
        for key,target in targets.items():
            if row[target]!='':continue
            fills.append(dict(column=target,value=entry[key],sha=native['source_sha256'],
                locator='codebook '+cfg['version']+'; exact text from '+source,
                method='APPROVED_CODEBOOK_'+cfg['version']+'_FROM_'+source,
                scope=canonical(dict(codebook_version=cfg['version'],codebook_sha256=book['sha256'],
                    approved_by=cfg['approved_by'],approved_date=cfg['approved_date'],source_column=source,
                    source_value=text,source_provenance=native))))
    return fills


def draft_codebook(rows):
    """List every native text/count; suggestions are explicitly unapproved codes."""
    # Suggestions are intentionally limited; uncertain geology/study progress is UNMAPPED.
    deposit={
        'D_CARBONATITE':{'Apatite/carbonatite','Carbonatite/monazite','Carbonatite/weathered','carbonatite intrusions','ferrocarbonatite'},
        'D_CLAY_REGOLITH':{'Clay hosted','Clay/regolith','Regolith/clay','Rare Earth Elements (REE) hosted in clays','clay-hosted','clay horizon','weathered clay horizon','saprolitic clays'},
        'D_IONIC_CLAY':{'Ion-adsorption clay (IAC) host rock','Ionic Clay-Hosted','Ionic adsorption clay','ionic clay-hosted'},
        'D_MINERAL_SANDS':{'HMS placer deposits','Mineral Sands','Mineral sands / monazite-xenotime','mineral sands','heavy mineral sands','sheet-style HMS','traditional mineral sands deposit'},
        'D_IRONSTONE':{'Ironstone'},'D_XENOTIME_HARD_ROCK':{'Xenotime hard rock'}}
    cfg=dict(version='v1',status='DRAFT',approved_by=None,approved_date=None,
        code_semantics='Proposed mnemonic research codes; no approved taxonomy or current-status assertion.',
        matching='EXACT_FULL_TEXT_INCLUDING_DISCLOSURE_DATE;NO_FUZZY_MATCH',deposit_type={},development_stage={})
    for group,(source,_) in FIELDS.items():
        for text,count in sorted(Counter(r[source] for r in rows if r[source]).items()):
            code=category=None
            if group=='deposit_type':
                code=next((c for c,values in deposit.items() if text in values),None)
            else:
                label=text.split('（')[0]
                if label in {'Exploration','Early exploration','Initial field reconnaissance','REE Exploration','Rare Earth Exploration',
                             'advanced exploration project','early exploration activities','exploration activities',
                             'exploration focus','ongoing exploration activities','very early-stage'}:
                    code,category='S_EXPLORATION','勘探（來源揭露時點）'
                elif label in {'Scoping Study','Scoping Study Update','Scoping','已揭露完成 Scoping Study'}:
                    code,category='S_SCOPING','概略研究（來源揭露時點）'
                elif label=='已揭露完成 PFS':code,category='S_PFS','預可行性研究（來源揭露時點）'
                elif label=='已揭露完成 DFS':code,category='S_DFS','可行性研究（來源揭露時點）'
                elif label in {'Operating','started production','Mining has now commenced and heavy mineral concentrate has been produced'}:
                    code,category='S_OPERATING','營運（來源揭露時點）'
            entry=dict(count=count,status='MAPPED' if code else 'UNMAPPED',code=code,
                reason='DRAFT_SUGGESTION_REQUIRES_RESEARCHER_APPROVAL' if code else 'UNMAPPED_AMBIGUOUS_OR_NO_APPROVED_EQUIVALENT')
            if group=='development_stage':entry['category']=category
            cfg[group][text]=entry
    return cfg
