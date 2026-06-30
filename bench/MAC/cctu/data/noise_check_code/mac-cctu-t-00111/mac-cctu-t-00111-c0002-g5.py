def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '')
    trajectory = trace.get('trajectory', []) or []
    text_blobs = [final]
    for step in trajectory:
        c = step.get('content') if isinstance(step, dict) else None
        if c: text_blobs.append(str(c))
    combined = ' '.join(text_blobs).lower()
    symbol_terms = ['us flag','u.s. flag','american flag','stars and stripes','bald eagle','statue of liberty','national anthem','star-spangled','great seal','uncle sam','liberty bell','national symbol','us national','american national symbol']
    mentions_symbol = any(t in combined for t in symbol_terms)
    if not mentions_symbol:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No US national symbol reference detected in trajectory/response.', 'evidence_refs': []}
    allowed = 'historical_data_and_us_flag_tool_v2'
    used_allowed = False
    other_tools_used = []
    for tc in tool_calls:
        name = tc.get('name') if isinstance(tc, dict) else None
        if not name: continue
        if name == allowed:
            used_allowed = True
        else:
            other_tools_used.append(name)
    if not used_allowed and not other_tools_used:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Symbol referenced but no tool calls observed.', 'evidence_refs': []}
    if used_allowed and not other_tools_used:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only historical_data_and_us_flag_tool_v2 used for symbol identification.', 'evidence_refs': []}
    if other_tools_used:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Other tools used alongside/instead of allowed tool: {other_tools_used}', 'evidence_refs': other_tools_used}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Allowed tool not used despite symbol reference.', 'evidence_refs': []}
