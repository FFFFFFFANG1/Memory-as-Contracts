def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    assistant_turns = [s for s in traj if (s.get('role','assistant')=='assistant')]
    total_turns = len(assistant_turns) if assistant_turns else len(traj)
    max_distinct = 0
    batch_turn_idx = -1
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        names = {c.get('name') for c in calls if c.get('name')}
        if len(names) > max_distinct:
            max_distinct = len(names)
            batch_turn_idx = i
    batched_ok = max_distinct >= 5
    turns_ok = total_turns <= 3
    followed = batched_ok and turns_ok
    return {'observed_followed': bool(followed),'confidence':'high' if (batched_ok and turns_ok) or (not batched_ok and len(traj)>0) else 'medium','reason': f'max_distinct_tools_in_turn={max_distinct} (need>=5), total_turns={total_turns} (need<=3)','evidence_refs':[{'turn_index':batch_turn_idx,'distinct_tools':max_distinct,'total_turns':total_turns}]}
