def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    length_ok = len(resp) >= 500
    # Section headers: markdown headers (#, ##) or underlined or ALL CAPS lines, or 'Section:' patterns
    lines = resp.splitlines()
    header_patterns = [
        re.compile(r'^\s{0,3}#{1,6}\s+\S'),
        re.compile(r'^[A-Z][A-Za-z0-9 ,/&-]{2,80}:\s*$'),
        re.compile(r'^\s*\d+\.\s+[A-Z][^\n]{2,}$'),
        re.compile(r'^[A-Z][A-Z0-9 \-/]{3,}$'),
    ]
    header_count = 0
    for ln in lines:
        for p in header_patterns:
            if p.match(ln):
                header_count += 1
                break
    headers_ok = header_count >= 2
    # No bold elements: detect **text** or __text__ markdown bold
    bold_re = re.compile(r'(\*\*[^*\n]+\*\*)|(__[^_\n]+__)')
    has_bold = bool(bold_re.search(resp))
    no_bold_ok = not has_bold
    followed = length_ok and headers_ok and no_bold_ok
    reason = f'length={len(resp)} headers={header_count} has_bold={has_bold}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if followed or has_bold or not length_ok else 'medium', 'reason': reason, 'evidence_refs': []}
