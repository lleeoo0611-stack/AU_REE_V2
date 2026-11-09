"""Write a current-only coverage and integrity review (no historical bundle)."""
import argparse,json
from pathlib import Path
from au_ree_v2.iteration_review import audit_summary
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--results',required=True);p.add_argument('--out',required=True)
a=p.parse_args();report=audit_summary(a.results);Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(report,ensure_ascii=False,indent=2))
