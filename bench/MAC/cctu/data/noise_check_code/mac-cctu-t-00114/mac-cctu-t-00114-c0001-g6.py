def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_steps = []  # list of (step_index, num_tool_calls, content)
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            tool_steps.append((i, len(tcs), (step.get('content') or '').strip()))
    if not tool_steps:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no tool calls in trajectory', 'evidence_refs':[]}
    # Check no parallel batching: each step has exactly one tool call
    parallel = [s for s in tool_steps if s[1] > 1]
    if parallel:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'parallel batching detected at step(s) {[s[0] for s in parallel]}', 'evidence_refs':[s[0] for s in parallel]}
    # Check each call preceded by written reflection on prior observation
    # First call: reflection not strictly required (no prior observation), but skip
    missing = []
    for idx, (step_i, _, content) in enumerate(tool_steps):
        if idx == 0:
            continue
        # reflection should be in this step's content (before tool call) or in an assistant message between prior tool result and this call
        reflection_text = content
        # also check any assistant messages between previous tool step and current
        prev_step_i = tool_steps[idx-1][0]
        between = []
        for j in range(prev_step_i+1, step_i+1):
            c = (traj[j].get('content') or '').strip()
            if c:
                between.append(c)
        combined = ' '.join(between).strip()
        if not combined or len(combined) < 20:
            missing.append(step_i)
    if missing:
        return {'observed_followed': False, 'confidence':'medium', 'reason': f'tool calls at steps {missing} lack written reflection on prior observation', 'evidence_refs': missing}
    return {'observed_followed': True, 'confidence':'medium', 'reason':'sequential calls with reflections preceding each subsequent call', 'evidence_refs':[s[0] for s in tool_steps]}
