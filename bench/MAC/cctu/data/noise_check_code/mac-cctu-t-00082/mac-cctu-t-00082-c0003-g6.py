def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    sc_calls = [t for t in tool_calls if (t.get('name') or '') == 'species_counter']
    if not sc_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'species_counter not invoked; cannot assess CI reporting', 'evidence_refs': []}
    # Look for mention of count and a confidence interval indicator
    has_count = bool(re.search(r'\b\d+\b', final))
    ci_patterns = [r'±', r'\+/-', r'\bCI\b', r'confidence interval', r'95%', r'\[\s*\d+\.?\d*\s*,\s*\d+\.?\d*\s*\]', r'variance', r'std(?:\.|dev)?']
    has_ci = any(re.search(p, final, re.IGNORECASE) for p in ci_patterns)
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    if has_count and has_ci:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'species count reported with confidence interval indicator', 'evidence_refs': ['final_response']}
    if has_count and not has_ci:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'species counts reported without confidence interval', 'evidence_refs': ['final_response']}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'no explicit species count found in response', 'evidence_refs': ['final_response']}
