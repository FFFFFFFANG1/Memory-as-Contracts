def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    used = [tc for tc in tool_calls if tc.get('name') == 'election_result_analyzer']
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'election_result_analyzer not invoked; constraint not applicable here.', 'evidence_refs': []}
    final = (trace.get('final_response') or '')
    low = final.lower()
    moe_patterns = [r'margin of error', r'\bmoe\b', r'±\s*\d', r'\+/-\s*\d', r'plus or minus']
    sample_patterns = [r'sample size', r'\bn\s*=\s*\d', r'sampled\s+\d', r'respondents', r'surveyed\s+\d']
    has_moe = any(re.search(p, low) for p in moe_patterns)
    has_sample = any(re.search(p, low) for p in sample_patterns)
    followed = has_moe and has_sample
    return {'observed_followed': bool(followed), 'confidence': 'high' if followed else 'medium', 'reason': f'margin_of_error_disclosed={has_moe}, sample_size_disclosed={has_sample}', 'evidence_refs': []}
