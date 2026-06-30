def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = text.splitlines()
    bullet_lines = [l for l in lines if re.match(r'\s*([-*+•]|\d+\.)\s+', l)]
    if len(bullet_lines) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no bullet list found', 'evidence_refs': []}
    low = text.lower()
    has_elev = bool(re.search(r'\b\d[\d,\.]*\s*(m|meter|meters|metre|metres|ft|feet)\b', low))
    has_area = any(k in low for k in ['national park','reserve','protected area','wilderness','sanctuary','conservation','monument','preserve'])
    if has_elev and has_area:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'bullets with elevation and protected area present', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'missing elevation={not has_elev} or protected area={not has_area}', 'evidence_refs': []}
