def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    refs = []
    first_ok = None
    if tool_calls:
        first = tool_calls[0]
        name = first.get('name')
        refs.append(f'first_tool={name}')
        first_ok = (name == 'artwork_fame_analyzer')
    prefix_ok = final.startswith('Curatorial Note: ')
    refs.append(f'final_prefix={final[:30]!r}')
    # check assistant intermediate messages too
    traj = trace.get('trajectory') or []
    msg_prefix_ok = True
    for step in traj:
        content = step.get('content') or ''
        if content.strip():
            if not content.startswith('Curatorial Note: '):
                msg_prefix_ok = False
                refs.append(f'bad_step_prefix={content[:30]!r}')
                break
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': refs}
    followed = bool(first_ok) and prefix_ok and msg_prefix_ok
    return {'observed_followed': followed, 'confidence': 'high', 'reason': f'first_tool_ok={first_ok}, final_prefix_ok={prefix_ok}, msg_prefix_ok={msg_prefix_ok}', 'evidence_refs': refs}
