def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Detect seating capacity figures or mentions
    seat_patterns = [
        r'seat(s|ing)?\s*(capacity|count|number)?\s*[:\-]?\s*\d',
        r'capacity\s*(of|:|\-)?\s*\d+\s*(seats|persons|people|patrons)?',
        r'\d{2,}\s*[- ]?seats?\b',
        r'\d{2,}\s*[- ]?seater\b',
        r'holds\s+\d{2,}\s*(people|patrons|spectators|guests)',
        r'accommodat(es|ing)\s+\d{2,}',
    ]
    hits = []
    for pat in seat_patterns:
        m = re.search(pat, low)
        if m:
            hits.append(m.group(0))
    if hits:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Seating capacity figures present: ' + '; '.join(hits[:3]), 'evidence_refs': []}
    # Check for heritage rating mention as positive signal
    heritage_terms = ['heritage', 'listed', 'grade i', 'grade ii', 'grade 1', 'grade 2', 'national register', 'landmark', 'protected', 'monument', 'historic register', 'architectural rating']
    has_heritage = any(t in low for t in heritage_terms)
    if not has_heritage:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No seating figures found but no clear heritage rating either', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No seating-capacity figures detected; heritage rating referenced', 'evidence_refs': []}
