def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    tools = ['aquarium_species_identifier','cultural_practice_identifier','economic_data_retriever','founder_association_finder','landmark_structure_finder','marine_biologist_finder','marine_ecosystem_locator','philanthropy_tracker','pulitzer_music_award_search','research_location_identifier']
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if not bullets:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No bulleted list detected', 'evidence_refs': lines[:3]}
    non_bullets = [l for l in lines if not bullet_re.match(l)]
    if len(non_bullets) > len(bullets):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Response is not primarily a bulleted list', 'evidence_refs': non_bullets[:3]}
    bad = []
    for b in bullets:
        m = re.search(r'\(([^()]+)\)\s*[.!?]?\s*$', b)
        if not m:
            bad.append(b)
            continue
        inside = m.group(1).strip()
        if not any(t in inside for t in tools):
            bad.append(b)
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Bullets missing trailing (tool_name) citation', 'evidence_refs': bad[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'All bullets end with a tool-name citation in parentheses', 'evidence_refs': bullets[:2]}
