def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls executed; cannot assess pre-tool plan requirement.', 'evidence_refs': []}
    # Find first tool call iteration/index
    first_iter = None
    for tc in tool_calls:
        it = tc.get('iteration')
        idx = tc.get('index')
        key = (it if it is not None else 0, idx if idx is not None else 0)
        if first_iter is None or key < first_iter:
            first_iter = key
    # Collect assistant text prior to first tool call
    pre_text_parts = []
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        if tcs:
            if content:
                pre_text_parts.append(content)
            break
        if content:
            pre_text_parts.append(content)
    pre_text = '\n'.join(pre_text_parts).lower()
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written plan produced before first tool call.', 'evidence_refs': ['trajectory[0]']}
    plan_kw = ['plan','decompos','step','approach','strategy','outline']
    dep_kw = ['depend','then','after','before','first','next','order','sequence','requires','based on']
    tool_names = ['artwork_information_retriever','bestselling_novel_finder','city_feature_identifier','cultural_landmark_finder','film_award_winner_finder','financial_data_retriever','geographical_feature_identifier','geological_verification_finder','historical_event_finder','historical_event_locator','historical_landmark_identifier','museum_locator','personal_location_finder','species_record_locator','venue_information_retriever']
    has_plan = any(k in pre_text for k in plan_kw)
    has_dep = any(k in pre_text for k in dep_kw)
    mentioned = [t for t in tool_names if t in pre_text or t.replace('_',' ') in pre_text]
    has_tools = len(mentioned) >= 1
    approved = any(w in pre_text for w in ['approved','confirm','proceed','go ahead','ok to proceed'])
    score = sum([has_plan, has_dep, has_tools])
    if score >= 2 and has_tools:
        followed = True
        conf = 'medium'
        reason = f'Pre-tool text includes plan/dependency language and mentions tools: {mentioned[:3]}. Approval signal={approved}.'
    elif score >= 1:
        followed = False
        conf = 'low'
        reason = 'Pre-tool text lacks full decomposition (plan, dependencies, listed tools).'
    else:
        followed = False
        conf = 'medium'
        reason = 'No decomposition plan with tool list and dependencies found before first tool call.'
    return {'observed_followed': followed, 'confidence': conf, 'reason': reason, 'evidence_refs': []}
