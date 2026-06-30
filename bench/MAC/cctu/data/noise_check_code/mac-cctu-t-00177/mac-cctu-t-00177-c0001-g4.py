def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', text)
    num_re = re.compile(r'(?<![A-Za-z_])\d[\d,]*(?:\.\d+)?')
    citation_markers = ['source:', 'source ', 'according to', 'cited', 'citation', 'per ', '[', 'ref:', 'reference', '(http', 'wikipedia', 'retrieved from', 'as reported', 'from the']
    unit_hint = re.compile(r'\d[\d,]*(?:\.\d+)?\s*[A-Za-z%°]')
    offenders = []
    checked = 0
    for s in sentences:
        s_stripped = s.strip()
        if not s_stripped:
            continue
        nums = num_re.findall(s_stripped)
        if not nums:
            continue
        checked += 1
        low = s_stripped.lower()
        has_citation = any(m in low for m in citation_markers)
        has_unit = bool(unit_hint.search(s_stripped)) or any(w in low for w in [' km',' mile',' meter',' year',' people',' percent','%',' usd',' eur',' books',' works',' monuments',' authors',' films',' residences',' landmarks',' capitals',' cities'])
        complete = s_stripped.endswith('.') or s_stripped.endswith('!') or s_stripped.endswith('?')
        if not (has_citation and has_unit and complete):
            offenders.append({'sentence': s_stripped[:200], 'has_citation': has_citation, 'has_unit': has_unit, 'complete': complete})
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no numeric outputs detected', 'evidence_refs': []}
    if offenders:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(offenders)}/{checked} numeric sentences missing unit/citation/completeness', 'evidence_refs': offenders[:5]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'all {checked} numeric sentences include units and citations', 'evidence_refs': []}
