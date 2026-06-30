def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tools = ['award_winner_finder','chef_dish_finder','delta_port_locator','landmark_country_locator','local_cuisine_explorer','location_identifier','organization_locator','person_location_finder','port_locator','professor_identifier','seafood_origin_locator','stone_origin_locator','supplier_store_linker']
    pre_audit_text = ''
    first_tool_step = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_step = i
            break
        pre_audit_text += '\n' + (step.get('content') or '')
    if first_tool_step is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present; cannot confirm pre-call audit context.', 'evidence_refs': []}
    text_low = pre_audit_text.lower()
    if not text_low.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No assistant content before first tool call; no audit recorded.', 'evidence_refs': [{'step_index': first_tool_step}]}
    mentioned = [t for t in tools if t.lower() in text_low]
    budget_terms = ['budget','remaining','calls left','call limit','quota','allowance','max call','uses left','remaining call']
    has_budget = any(term in text_low for term in budget_terms)
    # Check that budget info is associated with multiple tools (audit of inventory)
    if len(mentioned) >= max(3, len(tools)//2) and has_budget:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Pre-call audit mentions {len(mentioned)} tools with budget terminology.', 'evidence_refs': [{'step_index': first_tool_step, 'tools_mentioned': mentioned}]}
    if has_budget and len(mentioned) >= 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Budget mentioned but only {len(mentioned)} tools listed; not a full inventory audit.', 'evidence_refs': [{'step_index': first_tool_step, 'tools_mentioned': mentioned}]}
    if not has_budget:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No remaining-call-budget audit found before first retrieval call.', 'evidence_refs': [{'step_index': first_tool_step}]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Pre-call content lacks comprehensive tool budget audit.', 'evidence_refs': [{'step_index': first_tool_step}]}
