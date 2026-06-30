def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if len(resp) > 200:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'response length {len(resp)} exceeds 200 chars', 'evidence_refs': []}
    lines = [l.strip() for l in resp.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^([\-\*\u2022\u2013\u2014]|\d+[.)])\s+', l)]
    non_bullets = [l for l in lines if l not in bullets]
    if not bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bulleted list detected', 'evidence_refs': []}
    if len(non_bullets) > 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'non-bullet content present', 'evidence_refs': [str(non_bullets)[:200]]}
    tool_names = [tc.get('name','') for tc in trace.get('tool_calls', []) if tc.get('name')]
    known_tools = set(tool_names) | {'astronomical_discovery_finder','disaster_impact_analyzer','email_query_tool','event_location_finder','event_participation_finder','geopolitical_event_finder','historical_event_retriever','space_mission_info_retriever','sports_event_winner_retriever'}
    missing = []
    for b in bullets:
        cited = False
        low = b.lower()
        for t in known_tools:
            if t and t.lower() in low:
                cited = True; break
        if not cited:
            # accept generic tool-citation patterns like (tool: X) or [source: X]
            if re.search(r'(tool|source|via|from)\s*[:\-]', low) or re.search(r'\(([^)]*tool[^)]*)\)', low):
                cited = True
        if not cited:
            missing.append(b)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bullets missing tool citation', 'evidence_refs': missing[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'bulleted, cited, within 200 chars', 'evidence_refs': []}
