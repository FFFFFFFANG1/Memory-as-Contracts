def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    saw_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not saw_tool:
            if content:
                pre_text += '\n' + content
            if tcs:
                saw_tool = True
                break
    if not saw_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written content before first tool call', 'evidence_refs': []}
    text_low = pre_text.lower()
    known_tools = ['advanced_calculator','artifact_info_retriever','cultural_geography_mapper','cultural_highlight_locator','event_location_identifier','exploration_history_finder','historical_filmmaker_search','historical_monument_counter','landmark_info_retriever','literary_author_finder','residence_locator']
    tools_mentioned = [t for t in known_tools if t.lower() in text_low]
    # Look for sub-question structure: multiple list items or numbered questions
    items = re.findall(r'(?m)^\s*(?:[-*\u2022]|\d+[.)])\s+', pre_text)
    questions = re.findall(r'\?', pre_text)
    has_decomposition = len(items) >= 2 or len(questions) >= 2
    has_tools = len(tools_mentioned) >= 2
    if has_decomposition and has_tools:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Pre-tool decomposition with {len(items)} items and tool refs: {tools_mentioned}', 'evidence_refs': []}
    if not has_decomposition:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No clear sub-question list before first tool call', 'evidence_refs': []}
    if not has_tools:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Decomposition lacks explicit required tool names', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'Insufficient evidence of decomposition+tool mapping', 'evidence_refs': []}
