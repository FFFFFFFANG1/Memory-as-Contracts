def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Find index of first tool call in trajectory
    first_tool_step = None
    pre_text_parts = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_step = i
            # include content of same step BEFORE tool calls only if it precedes; treat as pre-text
            if content:
                pre_text_parts.append(content)
            break
        if content:
            pre_text_parts.append(content)
    if first_tool_step is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls found in trajectory','evidence_refs':[]}
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool text/roadmap recorded before first tool call','evidence_refs':[]}
    # Detect numbered list: at least 2 numbered items like '1.' '2.' or '1)' '2)'
    nums = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', pre_text)
    has_numbered = len(set(nums)) >= 2 and '1' in nums
    # Detect tool name mentions
    tool_names = ['elevation_finder','geographical_feature_identifier','historical_event_locator','historical_geography_associator','landmark_age_retriever','philosopher_identifier','poet_identifier','political_leader_identifier']
    mentioned = [t for t in tool_names if t.lower() in pre_text.lower() or t.replace('_',' ').lower() in pre_text.lower()]
    if not has_numbered:
        return {'observed_followed': False, 'confidence':'high','reason':'No numbered roadmap detected before first tool call','evidence_refs':[pre_text[:200]]}
    if not mentioned:
        return {'observed_followed': False, 'confidence':'medium','reason':'Numbered list present but no required tool referenced in roadmap','evidence_refs':[pre_text[:200]]}
    return {'observed_followed': True, 'confidence':'high','reason':'Numbered roadmap with tool references precedes first tool call','evidence_refs':[f'numbered_items={len(nums)}, tools_mentioned={mentioned}']}
