def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    # Collect ordered events: tool results and assistant text between calls
    # Strategy: iterate steps; for each step with tool_calls, the prior assistant content
    # should contain verbatim text of all prior unreflected tool results.
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    # Build a linear timeline from trajectory
    timeline = []  # list of ('text', str) or ('result', str)
    for step in traj:
        content = step.get('content') or ''
        if content:
            timeline.append(('text', str(content)))
        for tc in step.get('tool_calls') or []:
            timeline.append(('call', tc.get('name','')))
            res = tc.get('result')
            if res is not None:
                timeline.append(('result', str(res)))
    if not any(t[0]=='result' for t in timeline):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool results in trajectory', 'evidence_refs': []}
    pending_results = []
    violations = []
    checked = 0
    for kind, val in timeline:
        if kind == 'result':
            pending_results.append(val)
        elif kind == 'text':
            # reflection block — check all pending results verbatim
            for r in pending_results:
                checked += 1
                if r and r not in val:
                    violations.append(r[:80])
            pending_results = []
        elif kind == 'call':
            # a new tool call issued; any pending results were not reflected
            for r in pending_results:
                checked += 1
                violations.append('unreflected_before_call:' + r[:60])
            pending_results = []
    if checked == 0:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Could not align reflections with results', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(violations)} tool result(s) not repeated verbatim in reflection before next call', 'evidence_refs': violations[:3]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All tool results appear verbatim in reflection before subsequent tool calls', 'evidence_refs': []}
