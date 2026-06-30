def evaluate(trace):
    import re
    tcs = trace.get('tool_calls', []) or []
    primary = [t for t in tcs if t.get('name') in ('landmark_age_retriever','elevation_finder')]
    if not primary:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No landmark_age_retriever or elevation_finder calls; constraint not triggered.', 'evidence_refs': []}
    other_tools = [t for t in tcs if t.get('name') not in ('landmark_age_retriever','elevation_finder')]
    final = (trace.get('final_response') or '')
    has_appendix = bool(re.search(r'verification appendix|verification\s*[:\-]|appendix', final, re.I))
    corroborated = len(other_tools) >= len(primary)
    followed = corroborated and has_appendix
    reason = f'primary={len(primary)}, other_tool_calls={len(other_tools)}, appendix_found={has_appendix}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
