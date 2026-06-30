def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [l for l in resp.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^\s*([-*\u2022]|\d+[.)])\s+', l)]
    if len(bullet_lines) < 2 or len(bullet_lines) < max(1, len(lines)//2):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Response is not a bulleted list', 'evidence_refs': []}
    # Look for citations referencing tool responses on bullet lines
    citation_pat = re.compile(r'(\[[^\]]*(tool|source|ref|response|call)[^\]]*\]|\(([^)]*(tool|source|ref|response|call)[^)]*)\)|tool[_ ]?\d+|source\s*[:#]?\s*\w+|\[\d+\])', re.IGNORECASE)
    cited = [l for l in bullet_lines if citation_pat.search(l)]
    if len(cited) < len(bullet_lines):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(cited)}/{len(bullet_lines)} bullets have citations to tool responses', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Bulleted list with citations on each bullet', 'evidence_refs': []}
