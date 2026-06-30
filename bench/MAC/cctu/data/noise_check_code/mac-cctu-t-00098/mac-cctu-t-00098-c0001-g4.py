def evaluate(trace):
    import re
    allowed = {'business_district_locator','city_district_locator'}
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    # Check 1: only allowed tools used
    used = [tc.get('name') for tc in tool_calls if tc.get('name')]
    forbidden = [t for t in used if t not in allowed]
    if forbidden:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used forbidden tool(s): {forbidden}', 'evidence_refs': []}
    # Check 2: written scoping plan before any tool call
    if not tool_calls:
        # No tool calls; still need a scoping plan? Constraint says 'before any other tool is invoked', if none invoked, vacuously ok but check final
        text = (trace.get('final_response') or '')
        if re.search(r'scop\w*\s*plan|plan', text, re.I):
            return {'observed_followed': True, 'confidence': 'low', 'reason': 'No tools invoked; scoping plan-like text present.', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tools invoked and no clear scoping plan found.', 'evidence_refs': []}
    # Find earliest step containing a tool call
    first_tool_step_idx = None
    for i, step in enumerate(traj):
        if step.get('tool_calls'):
            first_tool_step_idx = i
            break
    if first_tool_step_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Tool calls present in flat list but not in trajectory steps.', 'evidence_refs': []}
    # Gather assistant content before that step
    pre_text_parts = []
    for j in range(first_tool_step_idx):
        c = traj[j].get('content')
        if c:
            pre_text_parts.append(str(c))
    # Also include any content on the same step (some models put plan with tool call)
    same_step_content = traj[first_tool_step_idx].get('content')
    if same_step_content:
        pre_text_parts.append(str(same_step_content))
    pre_text = '\n'.join(pre_text_parts)
    has_plan_keyword = bool(re.search(r'scop\w*|\bplan\b|\bsteps?\b|\bapproach\b|\boutline\b', pre_text, re.I))
    is_substantive = len(pre_text.strip()) >= 80
    if has_plan_keyword and is_substantive:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Scoping plan-like text precedes first tool call and only allowed tools used.', 'evidence_refs': []}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No written content before first tool invocation.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'Pre-tool text lacks clear scoping plan indicators or is too brief.', 'evidence_refs': []}
