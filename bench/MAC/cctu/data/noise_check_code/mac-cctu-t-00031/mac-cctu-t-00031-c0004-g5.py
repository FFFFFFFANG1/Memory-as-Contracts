def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    words = re.findall(r"\b\w+\b", text)
    wc = len(words)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pc = len(paragraphs)
    low = text.lower()
    has_pred = 'predecessor' in low
    has_succ = 'successor' in low
    has_coal = 'coalition' in low
    ok = wc >= 200 and pc >= 3 and has_pred and has_succ and has_coal
    reason = f'words={wc}, paragraphs={pc}, predecessor={has_pred}, successor={has_succ}, coalition={has_coal}'
    return {'observed_followed': bool(ok), 'confidence': 'high' if ok else 'medium', 'reason': reason, 'evidence_refs': []}
