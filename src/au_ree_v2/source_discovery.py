"""Parse candidate links and build bounded official source queries."""

import hashlib
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

from .security import sensitive_reference


def official_query(source,tasks):
    """A bounded WAMEX query from source-native candidates and confirmed aliases.

    No arbitrary year floor: released report metadata determines temporal scope.
    A configured year floor is allowed only with a recorded research rationale.
    """
    if not source.get('dynamic_candidates'):return source.get('where','1=1')
    if source.get('year_from') and not source.get('year_reason'):raise ValueError('REPORT_YEAR_RANGE_REQUIRES_RATIONALE')
    aliases=sorted({a.strip() for t in tasks if t.get('state')=='WA' for a in t['aliases'] if len(a.strip())>=4})
    if not aliases:return None
    terms=[]
    for alias in aliases:
        # LIKE metacharacters must be literal; leave punctuation/IDs in the
        # retained task, avoiding unbounded wildcard or SQL injection queries.
        safe=alias.replace("'","''").replace('%','').replace('_',' ')
        terms.extend("UPPER("+field+") LIKE '%"+safe.upper()+"%'" for field in ('project','title'))
    dates=(' AND report_year >= '+str(int(source['year_from']))) if source.get('year_from') else ''
    return "digital_file = 1"+dates+" AND ("+' OR '.join(terms)+") AND (UPPER(target_commodity) LIKE '%RARE EARTH%' OR UPPER(keywords) LIKE '%MONAZITE%' OR UPPER(keywords) LIKE '%METALLURG%' OR UPPER(keywords) LIKE '%MINERAL PROCESS%')"


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.current=None;self.row_text=None;self.row_links=[];self.link_dates={}
    def handle_starttag(self, tag, attrs):
        if tag=='a': self.current=[dict(attrs).get('href',''),'']
        if tag=='tr':self.row_text='';self.row_links=[]
    def handle_data(self, data):
        if self.current is not None:self.current[1]+=data
        if self.row_text is not None:self.row_text+=' '+data
    def handle_endtag(self, tag):
        if tag=='a' and self.current is not None:
            self.links.append(self.current);self.row_links.append(self.current[0]); self.current=None
        if tag=='tr' and self.row_text is not None:
            dates=re.findall(r'\b\d{2}/\d{2}/20\d{2}\b',self.row_text)
            if len(set(dates))==1:
                try:
                    date=datetime.strptime(dates[0],'%d/%m/%Y').date().isoformat()
                    self.link_dates.update({href:date for href in self.row_links})
                except ValueError:pass
            self.row_text=None;self.row_links=[]


def candidates(raw, seed):
    parser=Links(); parser.feed(raw.decode('utf-8',errors='replace'))
    rows={}
    for href,label in parser.links:
        url=urldefrag(urljoin(seed['url'],href))[0]
        host=urlsplit(url).hostname
        if urlsplit(url).scheme!='https' or host not in seed['allowed_hosts'] or sensitive_reference(url):continue
        if seed.get('keywords') and not any(k.casefold() in (url+' '+label).casefold() for k in seed['keywords']):continue
        if not re.search(seed.get('pattern',r'\.pdf(?:[?\s]|$)|displayAnnouncement\.do\?display=pdf'),url+' '+label,re.I):continue
        key=hashlib.sha256(url.encode()).hexdigest()
        rows[key]={'candidate_id':key,'url':url,'title':label.strip(),'seed_key':seed['key'],
                   'publication_date':parser.link_dates.get(href),'status':'DISCOVERED_NOT_OBSERVATION',
                   'authority':'ISSUER_LINKED_DELIVERY_NOT_CONTENT_VERIFIED' if seed.get('authority')=='ISSUER' else 'SOURCE_AUTHORITY_NOT_ESTABLISHED',
                   'project_id':seed.get('project_id'),'identity_status':'SOURCE_CONTEXT_ONLY_NOT_EQUIVALENCE'}
    return list(rows.values())


def strict_search_plan(root):
    """Bounded official queries shared by ASX acquisition and its dry-run plan."""
    path = Path(root) / 'config/discovery.json'
    policy = json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    fixed, deferred = [], []
    for report in policy.get('official_reports', []):
        if report['protocol'] == 'arcgis' and not report.get('where'):
            deferred.append(report)
        else:
            fixed.append(dict(report, dynamic_candidates=False, resume=False))
    return dict(policy, official_reports=fixed, official_cursors={}), deferred
