def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tools = trace.get('tool_calls') or []
    if not tools:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory', 'evidence_refs': []}
    tool_names = ['election_results_analyzer','event_outcome_retriever','historical_event_data_retriever','historical_event_finder','incident_info_retriever','international_organization_event_tracker','outbreak_case_tracker','public_domain_calculator','space_mission_identifier','sports_event_winner_finder']
    pre_text = ''
    found_first_call = False
    for step in traj:
        if step.get('tool_calls'):
            found_first_call = True
            break
        c = step.get('content') or ''
        pre_text += '\n' + c
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No content before first tool call', 'evidence_refs': []}
    lines = pre_text.splitlines()
    bullets = [l for l in lines if re.match(r'^\s*([\-\*\u2022]|\d+[\.\)])\s+', l)]
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found {len(bullets)} bullets in pre-tool roadmap', 'evidence_refs': bullets}
    used_tools = []
    seen = set()
    for t in tools:
        n = t.get('name')
        if n and n not in seen:
            seen.add(n); used_tools.append(n)
    bullets_with_tool = 0
    missing = []
    for b in bullets:
        if any(tn in b for tn in tool_names):
            bullets_with_tool += 1
        else:
            missing.append(b)
    if bullets_with_tool < len(bullets):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(missing)} bullet(s) do not reference a specific tool', 'evidence_refs': missing[:3]}
    referenced = set()
    for b in bullets:
        for tn in tool_names:
            if tn in b:
                referenced.add(tn)
    missing_calls = [u for u in used_tools if u not in referenced]
    if missing_calls:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tools called but not in roadmap: {missing_calls}', 'evidence_refs': bullets}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Bulleted roadmap present before tool calls with tool references covering used tools', 'evidence_refs': bullets[:5]}
