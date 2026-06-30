def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    # Check for tables (markdown pipe tables)
    has_table = bool(re.search(r'\n\s*\|.*\|', text)) or bool(re.search(r'\|[-:\s|]+\|', text))
    # Check for bullet lists
    has_bullets = False
    for line in text.splitlines():
        s = line.lstrip()
        if re.match(r'^[-*+]\s+', s) or re.match(r'^\d+\.\s+', s):
            has_bullets = True
            break
    # Count sentences
    cleaned = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"\'])', cleaned)
    sentences = [p for p in parts if p.strip()]
    n = len(sentences)
    violations = []
    if has_table: violations.append('contains table')
    if has_bullets: violations.append('contains bullet/numbered list')
    if n > 3: violations.append(f'has {n} sentences (>3)')
    followed = len(violations) == 0
    return {'observed_followed': followed, 'confidence': 'high' if followed or violations else 'medium', 'reason': 'OK' if followed else '; '.join(violations), 'evidence_refs': []}
