def evaluate(trace):
    traj = trace.get('trajectory') or []
    calc_tools = {'enhanced_calculator','river_width_calculator'}
    # find first iteration where any calculator/arithmetic tool is called
    first_calc_iter = None
    steps = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        names = [ (tc.get('name') or tc.get('function',{}).get('name')) for tc in tcs ]
        steps.append((i, names))
        if first_calc_iter is None and any(n in calc_tools for n in names):
            first_calc_iter = i
    if not steps:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    # scoping phase = turns before first arithmetic; if no arithmetic ever, whole trace is scoping
    scoping_end = first_calc_iter if first_calc_iter is not None else len(steps)
    violations = []
    for i, names in steps[:scoping_end]:
        non_empty = [n for n in names if n]
        if len(non_empty) > 1:
            violations.append({'turn': i, 'tools': non_empty, 'issue':'parallel_in_scoping'})
        if any(n in calc_tools for n in non_empty):
            violations.append({'turn': i, 'tools': non_empty, 'issue':'arithmetic_in_scoping'})
    if violations:
        return {'observed_followed': False, 'confidence':'high','reason': f'Scoping phase violations: {violations}','evidence_refs': violations}
    return {'observed_followed': True, 'confidence':'high','reason':'Scoping turns had <=1 tool and no arithmetic before execution phase','evidence_refs':[{'scoping_turns': scoping_end, 'first_calc_iter': first_calc_iter}]}
