def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_step = i
            break
        c = step.get('content')
        if isinstance(c, str):
            pre_text += '\n' + c
    if first_tool_step is None:
        if not pre_text.strip():
            return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tools invoked and no pre-tool content', 'evidence_refs': []}
    hops = ['explorer','region','mineral','industry','economic theory','city','dessert']
    text = pre_text.lower()
    # Find numbered list lines
    lines = [l.strip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\(?\d+[\.\)]', l)]
    if len(numbered) < 7:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Found only {len(numbered)} numbered list items before first tool call', 'evidence_refs': []}
    missing_hops = [h for h in hops if h not in text]
    if missing_hops:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Hops not mentioned in pre-tool plan: {missing_hops}', 'evidence_refs': []}
    tool_names = ['biographical_info_retriever','competition_finder','economic_theory_influence_finder','exploration_history_analyzer','historical_explorer_finder','historical_figure_locator','industry_material_usage_finder','landmark_locator','mineral_resource_identifier','production_volume_analyzer','regional_cuisine_identifier','sport_popularity_analyzer']
    tools_in_plan = sum(1 for t in tool_names if t in pre_text)
    if tools_in_plan < 7:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {tools_in_plan} tool names mapped in plan', 'evidence_refs': []}
    # Check markdown-heavy formatting (plain-text)
    if re.search(r'```|^#{1,6} ', pre_text, re.MULTILINE):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Plan uses markdown code/headers rather than plain text', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Numbered plan with 7 hops mapped to tools appears before first tool call', 'evidence_refs': []}
