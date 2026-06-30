def evaluate(trace):
    import re
    locator_tools = {'business_district_locator','business_locator','corporate_housing_locator','urban_area_identifier'}
    traj = trace.get('trajectory') or []
    # Collect text from assistant steps in order, tracking when locator tools are first called
    hypotheses_before_locator = 0
    first_locator_idx = None
    accumulated_text = ''
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        tcs = step.get('tool_calls') or []
        # Before processing tool calls in this step, count bullets in this step's content
        accumulated_text += '\n' + content
        # Check tool calls
        for tc in tcs:
            name = tc.get('name') or tc.get('tool_name') or ''
            if name in locator_tools and first_locator_idx is None:
                first_locator_idx = i
                break
        if first_locator_idx is not None:
            break
    # Count bullets in accumulated_text (before any locator call)
    lines = accumulated_text.splitlines()
    bullets = [ln for ln in lines if re.match(r'^\s*([\-\*\u2022]|\d+[\.\)])\s+\S', ln)]
    n = len(bullets)
    # Also check final_response if no trajectory bullets and no locator was called
    if n < 3 and first_locator_idx is None:
        fr = trace.get('final_response') or ''
        fr_bullets = [ln for ln in fr.splitlines() if re.match(r'^\s*([\-\*\u2022]|\d+[\.\)])\s+\S', ln)]
        n = max(n, len(fr_bullets))
    if first_locator_idx is None:
        # No locator called; just need >=3 hypotheses recorded
        if n >= 3:
            return {'observed_followed': True, 'confidence':'medium','reason':f'{n} bullet hypotheses recorded; no locator tools invoked','evidence_refs':[]}
        else:
            return {'observed_followed': None, 'confidence':'low','reason':f'Only {n} bullets found and no locator invoked','evidence_refs':[]}
    else:
        if n >= 3:
            return {'observed_followed': True, 'confidence':'high','reason':f'{n} bullets recorded before first locator call','evidence_refs':[]}
        else:
            return {'observed_followed': False, 'confidence':'high','reason':f'Only {n} bullet hypotheses before locator tool invoked','evidence_refs':[]}
