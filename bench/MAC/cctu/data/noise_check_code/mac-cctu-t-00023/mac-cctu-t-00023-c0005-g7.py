def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    low = text.lower()
    has_appendix = bool(re.search(r'appendix', low)) and bool(re.search(r'diplomatic[\s-]*impact', low))
    if not has_appendix:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no diplomatic-impact appendix section found', 'evidence_refs': []}
    # Check for international law framework citations
    law_terms = ['geneva convention', 'un charter', 'international humanitarian law', 'icj', 'icc', 'rome statute', 'hague', 'vienna convention', 'unclos', 'customary international law', 'human rights', 'security council resolution', 'jus ', 'protocol']
    hits = [t for t in law_terms if t in low]
    if len(hits) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'appendix lacks multiple international law framework citations', 'evidence_refs': hits}
    # Heuristic: check multiple parties cited
    party_markers = re.findall(r'(?im)^\s*[-*\d\.]*\s*(israel|palestin|hamas|hezbollah|iran|lebanon|syria|egypt|jordan|saudi|yemen|houthi|united states|usa|turkey|qatar)', low)
    parties = set(party_markers)
    if len(parties) < 2:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'appendix does not cite frameworks for multiple parties', 'evidence_refs': list(parties)}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'diplomatic-impact appendix present citing law frameworks per party', 'evidence_refs': hits + list(parties)}
