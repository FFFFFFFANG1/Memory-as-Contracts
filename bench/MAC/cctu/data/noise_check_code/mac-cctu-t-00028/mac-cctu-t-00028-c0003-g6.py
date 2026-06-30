def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Find defendants section
    m = re.search(r'defendants?\s*[:\-]\s*(.+?)(?:\n\n|\Z)', text, re.IGNORECASE | re.DOTALL)
    names = []
    if m:
        segment = m.group(1)
        # split by commas, semicolons, newlines, ' and '
        parts = re.split(r',|;|\band\b|\n|\u2022|\*|\-\s', segment)
        for p in parts:
            n = p.strip().strip('.').strip()
            if n and len(n) < 120 and re.search(r'[A-Za-z]', n):
                names.append(n)
    if not names:
        # try bullet list of capitalized names
        bullets = re.findall(r'(?:^|\n)\s*(?:[-*\u2022]|\d+\.)\s+([A-Z][^\n]+)', text)
        names = [b.strip().strip('.') for b in bullets if b.strip()]
    has_merger_ref = bool(re.search(r'merger\s+(filing|application|notification|agreement|case|review|control|notice)|hsr|hart[- ]scott[- ]rodino|form\s*cco?|notification\s+of\s+merger', low))
    if not names:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'could not identify defendant list', 'evidence_refs': []}
    normalized = [n.lower() for n in names]
    is_sorted = normalized == sorted(normalized)
    if not is_sorted:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'defendants not alphabetical: {names}', 'evidence_refs': names}
    if not has_merger_ref:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no reference to originating merger filing', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'defendants alphabetical and merger filing referenced', 'evidence_refs': names}
