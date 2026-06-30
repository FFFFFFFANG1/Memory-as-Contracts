def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Filter likely item lines: skip headers/intro
    candidate = [l for l in lines if not l.endswith(':') and not re.match(r'^(here|the following|pantry|items|summary|note)\b', l, re.I)]
    if not candidate:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no item lines detected', 'evidence_refs': []}
    date_re = re.compile(r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4}|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s*\d{2,4})', re.I)
    qty_re = re.compile(r'(\b\d+(?:\.\d+)?\s*(?:x|pcs|pieces|units|cans|bottles|boxes|bags|jars|packs|lb|lbs|kg|g|oz|ml|l|count)?\b)', re.I)
    shelf_re = re.compile(r'(shelf\s*[A-Z0-9\-]+|\b[A-Z]\d{1,3}\b|aisle\s*\d+|rack\s*\w+|bin\s*\w+)', re.I)
    bad = []
    for l in candidate:
        has_date = bool(date_re.search(l))
        has_qty = bool(qty_re.search(l))
        has_shelf = bool(shelf_re.search(l))
        if not (has_date and has_qty and has_shelf):
            bad.append(l)
    if bad:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(bad)} line(s) missing qty/date/shelf: ' + ' | '.join(bad[:3]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'all {len(candidate)} item lines include qty, expiration date, and shelf id', 'evidence_refs': []}
