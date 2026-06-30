def evaluate(trace):
    import re
    geospatial = {'elevation_finder','geographical_feature_locator','landmark_locator','peak_identifier','event_host_locator','fishing_port_catch_analyzer'}
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    # find first geospatial tool call index
    first_geo_idx = None
    for tc in tcs:
        if tc.get('name') in geospatial:
            first_geo_idx = tc.get('index')
            break
    # gather assistant text content prior to first geospatial call
    pre_text_parts = []
    for step in traj:
        content = step.get('content') or ''
        step_tool_calls = step.get('tool_calls') or []
        has_geo_here = any((c.get('name') or (c.get('function',{}) or {}).get('name')) in geospatial for c in step_tool_calls)
        if has_geo_here:
            if content:
                pre_text_parts.append(content)
            break
        if content:
            pre_text_parts.append(content)
    pre_text = '\n'.join(pre_text_parts)
    if first_geo_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No geospatial tool was invoked; cannot verify pre-invocation checklist.', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant text preceded the first geospatial tool call.', 'evidence_refs': []}
    # detect numbered checklist: at least 2 lines starting with 1. 2. etc.
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^(\(?\d+[\.\)])\s+', l)]
    has_numbered = len(numbered) >= 2
    lower = pre_text.lower()
    mentions_tools = any(k in lower for k in ['tool','call','invoke','use '])
    mentions_facts = any(k in lower for k in ['fact','intermediate','need','require','information','data'])
    mentions_artifact = any(k in lower for k in ['checklist','scoping','plan','artifact'])
    followed = has_numbered and mentions_tools and mentions_facts and mentions_artifact
    reason = f'numbered={has_numbered} tools={mentions_tools} facts={mentions_facts} artifact_label={mentions_artifact}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
