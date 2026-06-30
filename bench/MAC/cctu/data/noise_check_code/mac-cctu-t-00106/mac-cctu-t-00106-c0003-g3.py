def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    calls = trace.get('tool_calls') or []
    cephalopod_terms = ['cephalopod','octopus','squid','cuttlefish','nautilus','tentacle','arm','mantle','beak','siphon','chromatophore']
    # find sentences with numbers and cephalopod terms
    sentences = re.split(r'(?<=[.!?])\s+', final)
    claims = []
    for s in sentences:
        if re.search(r'\d', s) and any(t in s.lower() for t in cephalopod_terms):
            claims.append(s)
    if not claims:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No numerical cephalopod anatomy claims detected.', 'evidence_refs': []}
    retriever_used = any((c.get('name') == 'factual_information_retriever') for c in calls)
    cite_pattern = re.compile(r'(\[[^\]]+\]|\(source[^)]*\)|cite|citation|source:|ref\.|reference)', re.IGNORECASE)
    missing_cite = [s for s in claims if not cite_pattern.search(s)]
    if not retriever_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Numerical cephalopod claims present but factual_information_retriever not called.', 'evidence_refs': claims[:3]}
    if missing_cite:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Some numerical claims lack citation notes.', 'evidence_refs': missing_cite[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Claims appear cited and retriever was used.', 'evidence_refs': claims[:3]}
