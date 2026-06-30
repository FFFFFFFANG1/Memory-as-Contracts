def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    saw_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            saw_tool = True
            break
        c = step.get('content')
        if isinstance(c, str):
            pre_text += '\n' + c
    if not saw_tool and not (trace.get('tool_calls') or []):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool invocation found; cannot assess pre-tool logging.', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Tools invoked without any prior content logging sub-tasks.', 'evidence_refs': []}
    low = pre_text.lower()
    has_subtasks = bool(re.search(r'(sub-?task|step\s*\d|task\s*\d|\d+\.|decompos)', low))
    has_tool_assign = bool(re.search(r'(tool\s*[:=]|assigned tool|use\s+\w+_\w+|→|->)', low))
    # check at least one available tool name mentioned
    tools = ['architectural_works_locator','conservation_award_winner_finder','festival_finder','individual_location_finder','local_specialty_identifier','nature_reserve_association_finder','resource_recipient_locator','river_locator','species_locator','sports_team_locator','zoological_research_finder']
    tool_mentioned = any(t in low for t in tools)
    has_deps = bool(re.search(r'(depend|dependenc|prerequisit|requires|after\s+(step|task)|none\b)', low))
    score = sum([has_subtasks, (has_tool_assign or tool_mentioned), has_deps])
    if score == 3:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Pre-tool content lists sub-tasks with assigned tools and dependencies.', 'evidence_refs': []}
    if score >= 2:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Partial decomposition logged before tool invocation.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-tool content lacks explicit sub-tasks, tool assignments, or dependencies.', 'evidence_refs': []}
