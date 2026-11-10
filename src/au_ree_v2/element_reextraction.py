"""Offline oxide table discovery. Candidates are never validated observations."""
import re
from .project_summary import ELEMENTS, MAGNET, HEAVY, complete_sum

SUBSCRIPTS = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')


def oxide_hints(text):
    normalized = text.translate(SUBSCRIPTS)
    found = [o for o in ELEMENTS if re.search(r'(?<![A-Za-z])'+r'\s*'.join(o)+r'(?![A-Za-z0-9])', normalized)]
    labels = []
    if re.search(r'JORC\s+(?:Code\s+)?Table\s*1', text, re.I): labels.append('JORC_TABLE_1')
    if re.search(r'(?:oxide|rare earth|REE)\s+(?:composition|distribution)', text, re.I): labels.append('OXIDE_DISTRIBUTION')
    return dict(oxides=found, labels=labels, extract_tables=len(found)>=2 or bool(labels))


def derivation_gaps(row):
    """Inventory only; all inputs must be present, never interpret missing as zero."""
    values = {}
    for oxide in ELEMENTS:
        token = next((v for k, v in row.items() if k.startswith(oxide+'_')), '')
        if token != '': values[oxide] = float(token)
    options = [
        ('NdPr蘊藏量_kt_需兩者皆公布', ('Nd2O3','Pr6O11')),
        ('完整重稀土組合蘊藏量_kt_需8元素皆公布', HEAVY),
        ('磁性元素重算值_NdPrTbDy_kt', MAGNET)]
    return [dict(column=column, value=complete_sum(values, required), inputs=list(required),
                 decision='REQUIRES_EXISTING_SAME_SCOPE_PROVENANCE_VALIDATION')
            for column, required in options if row[column]=='' and complete_sum(values, required) is not None]
