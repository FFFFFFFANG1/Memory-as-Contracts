def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'empty response', 'evidence_refs':[]}
    # Find numerical claims: numbers (with optional decimals, commas, %, years)
    # Split into sentences/lines and check each numeric occurrence
    num_pattern = re.compile(r'\b\d[\d,\.]*\s*%?')
    bracket_pattern = re.compile(r'\[[^\]]+\]')
    # For each number, check if there's a bracketed tag within the next ~80 chars before next number/sentence end
    missing = []
    for m in num_pattern.finditer(text):
        start = m.end()
        # Look ahead up to next sentence boundary or 120 chars
        window = text[start:start+150]
        # cut at next sentence terminator
        cut = re.search(r'[.!?\n]', window)
        scan = window[:cut.start()] if cut else window
        if not bracket_pattern.search(scan):
            # also check immediately before-after
            ctx = text[max(0,m.start()-5):start+30]
            if not bracket_pattern.search(ctx):
                missing.append((m.group(), m.start()))
    # Check for ranking commentary
    ranking_terms = ['most important','least important','best','worst','top-ranked','highest-ranked','lowest-ranked','ranked first','ranked second','ranked third','#1','number one','superior to','inferior to','outranks','outranked']
    lowered = text.lower()
    ranking_hits = [t for t in ranking_terms if t in lowered]
    followed = (len(missing) == 0) and (len(ranking_hits) == 0)
    reason_parts = []
    if missing:
        reason_parts.append(f'{len(missing)} numeric claim(s) lack bracketed source tag: {missing[:3]}')
    if ranking_hits:
        reason_parts.append(f'ranking commentary present: {ranking_hits}')
    if not reason_parts:
        reason_parts.append('all numeric claims tagged and no ranking commentary')
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': '; '.join(reason_parts), 'evidence_refs': []}
