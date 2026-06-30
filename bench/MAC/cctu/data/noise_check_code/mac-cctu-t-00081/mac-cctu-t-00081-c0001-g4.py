def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    reasons = []
    lines = response.splitlines()
    has_heading = any(re.match(r'^\s{0,3}#{1,6}\s+\S', ln) for ln in lines)
    if not has_heading:
        reasons.append('no markdown heading')
    has_bullet = any(re.match(r'^\s*[-*+]\s+\S', ln) for ln in lines)
    if not has_bullet:
        reasons.append('no bullet points')
    has_emphasis = bool(re.search(r'\*\*[^*\n]+\*\*', response)) or bool(re.search(r'__[^_\n]+__', response)) or bool(re.search(r'(?<!\*)\*[^*\n]+\*(?!\*)', response)) or bool(re.search(r'(?<!_)_[^_\n]+_(?!_)', response))
    if not has_emphasis:
        reasons.append('no emphasized terms')
    stripped = response.rstrip()
    if not stripped.endswith('.'):
        reasons.append('does not end with a period')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'markdown headings, bullets, emphasis present and ends with period', 'evidence_refs': []}
