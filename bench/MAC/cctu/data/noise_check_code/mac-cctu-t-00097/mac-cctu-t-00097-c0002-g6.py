def evaluate(trace):
    allowed = {'biographical_info_retriever','historical_fact_finder'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    forbidden = [n for n in used if n not in allowed]
    final = (trace.get('final_response') or '').strip()
    if forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {sorted(set(forbidden))}', 'evidence_refs': []}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to assess paragraph format.', 'evidence_refs': []}
    # Check it's a short paragraph: not bullets/headers, modest length
    import re
    has_bullets = bool(re.search(r'(^|\n)\s*([-*+]|\d+\.)\s+', final))
    has_headers = bool(re.search(r'(^|\n)#{1,6}\s', final))
    paragraphs = [p for p in re.split(r'\n\s*\n', final) if p.strip()]
    word_count = len(final.split())
    is_short = word_count <= 250
    is_paragraph = (len(paragraphs) <= 2) and not has_bullets and not has_headers
    if is_paragraph and is_short:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Tools restricted to allowed set; response is a short paragraph.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Response not a short biographical paragraph (words={word_count}, paragraphs={len(paragraphs)}, bullets={has_bullets}, headers={has_headers}).', 'evidence_refs': []}
