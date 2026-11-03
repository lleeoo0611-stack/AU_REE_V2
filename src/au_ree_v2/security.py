"""Publication guard for literal and repeatedly encoded credential query parameters."""
import html,re
from urllib.parse import unquote
PATTERN=re.compile(r'[?&]\s*(?:access[_\s-]*token|api[_\s-]*key|token|signature|sig)\s*=',re.I)
def sensitive_reference(text):
    for _ in range(8):text=html.unescape(unquote(text))
    return bool(PATTERN.search(text))
