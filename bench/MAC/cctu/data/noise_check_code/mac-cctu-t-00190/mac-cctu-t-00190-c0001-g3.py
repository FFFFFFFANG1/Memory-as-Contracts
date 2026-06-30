def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Find first assistant message that has tool_calls, and check content before it
    pre_text_parts = []
    first_tool_step_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_step_idx = i
            # include content of this step too (it precedes the tool call)
            if content:
                pre_text_parts.append(content)
            break
        else:
            if content:
                pre_text_parts.append(content)
    if first_tool_step_idx is None:
        # No tool calls were made; check final_response or pre text for outline anyway
        text = '\n'.join(pre_text_parts) or (trace.get('final_response') or '')
        if not text.strip():
            return {'observed_followed': None, 'confidence':'unknown','reason':'No content and no tool calls','evidence_refs':[]}
    else:
        text = '\n'.join(pre_text_parts)
    if not text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No text emitted before first tool call','evidence_refs':[]}
    # Detect numbered outline: at least two lines starting with 1. 2. or 1) 2)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\(?\d+[\.\)]\s+\S', l)]
    has_outline = len(numbered) >= 2
    # Check plain text (no heavy markdown like code fences or headers); allow simple text
    has_code_fence = '```' in text
    if has_outline and not has_code_fence:
        return {'observed_followed': True, 'confidence':'high','reason':f'Found {len(numbered)} numbered items before first tool call','evidence_refs':[]}
    if not has_outline:
        return {'observed_followed': False, 'confidence':'high','reason':'No numbered decomposition detected before first tool call','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':'Outline present but not plain-text (code fence found)','evidence_refs':[]}
