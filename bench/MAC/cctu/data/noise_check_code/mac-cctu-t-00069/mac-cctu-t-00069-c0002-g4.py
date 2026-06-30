def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    aai = [c for c in calls if c.get('name') == 'artist_artwork_identifier']
    count = len(aai)
    final = trace.get('final_response', '') or ''
    md_patterns = [r'\*\*', r'__', r'^#', r'\n#', r'`', r'\[[^\]]+\]\([^\)]+\)', r'^\s*[-*+]\s', r'\n\s*[-*+]\s']
    has_md = any(re.search(p, final) for p in md_patterns)
    if count != 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'artist_artwork_identifier called {count} times, expected exactly 1', 'evidence_refs': []}
    if has_md:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Final response contains Markdown formatting', 'evidence_refs': []}
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Empty final response', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Tool used once and response is plain text', 'evidence_refs': []}
