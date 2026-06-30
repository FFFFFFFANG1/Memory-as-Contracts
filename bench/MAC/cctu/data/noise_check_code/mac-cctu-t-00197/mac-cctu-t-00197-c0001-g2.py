def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    # Reject JSON wrappers
    stripped = text.lstrip()
    if stripped.startswith('{') or stripped.startswith('['):
        return {'observed_followed': False,'confidence':'high','reason':'Response appears wrapped in JSON','evidence_refs':[stripped[:60]]}
    if '```json' in text.lower() or re.search(r'\{\s*"', text):
        return {'observed_followed': False,'confidence':'high','reason':'Contains JSON wrapper','evidence_refs':[]}
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False,'confidence':'high','reason':'No content lines','evidence_refs':[]}
    header = lines[0].lower()
    required = ['venue','capacity','era','cultural significance']
    if ',' not in header:
        return {'observed_followed': False,'confidence':'high','reason':'Header not comma-separated','evidence_refs':[lines[0]]}
    cols = [c.strip().strip('"').lower() for c in header.split(',')]
    missing = [c for c in required if c not in cols]
    if missing:
        return {'observed_followed': False,'confidence':'high','reason':f'Missing columns: {missing}','evidence_refs':[lines[0]]}
    if cols[:4] != required:
        return {'observed_followed': False,'confidence':'medium','reason':f'Column order/extras: {cols}','evidence_refs':[lines[0]]}
    return {'observed_followed': True,'confidence':'high','reason':'CSV with required columns and no JSON wrapper','evidence_refs':[lines[0]]}
