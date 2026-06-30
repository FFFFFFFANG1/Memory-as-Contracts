def evaluate(trace):
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    steps_with_calls = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps_with_calls.append((i, len(tcs), (step.get('content') or '').strip()))
    if not steps_with_calls:
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    # Check one tool call per step
    for i, n, _ in steps_with_calls:
        if n > 1:
            return {'observed_followed': False,'confidence':'high','reason': f'step {i} has {n} tool calls in one turn','evidence_refs':[{'step':i}]}
    # Check reflection note between consecutive tool-calling steps
    indices = [i for i,_,_ in steps_with_calls]
    for a, b in zip(indices, indices[1:]):
        reflection = False
        for j in range(a+1, b):
            c = (traj[j].get('content') or '').strip()
            if c and not (traj[j].get('tool_calls')):
                reflection = True
                break
        # also accept assistant content on step a itself as the reflection before next
        if not reflection:
            mid_content = (traj[a].get('content') or '').strip()
            if mid_content and len(mid_content) > 10:
                reflection = True
        if not reflection:
            return {'observed_followed': False,'confidence':'medium','reason': f'no reflection note between tool calls at steps {a} and {b}','evidence_refs':[{'step_a':a,'step_b':b}]}
    return {'observed_followed': True,'confidence':'medium','reason':'one tool call per turn with reflections between','evidence_refs':[{'tool_steps':indices}]}
