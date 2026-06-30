def evaluate(trace):
    import re
    final = trace.get('final_response','') or ''
    calls = trace.get('tool_calls',[]) or []
    # Heuristic: 'initial scoping' = first iteration/early calls
    iters = [c.get('iteration') for c in calls if c.get('iteration') is not None]
    if iters:
        first_iter = min(iters)
        early = [c for c in calls if c.get('iteration')==first_iter]
    else:
        early = calls[:2] if len(calls)<=2 else calls
    early_count = len(early)
    count_ok = early_count <= 2
    # Detect bullet list in final response
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    bullets = [l for l in lines if re.match(r'^([-*+•]|\d+[.)])\s+', l)]
    has_bullets = len(bullets) >= 2
    # Look for plan-related wording near bullets
    plan_kw = re.search(r'\b(plan|next|will invoke|will call|next steps?|tools? to (use|invoke|call))\b', final, re.I) is not None
    followed = count_ok and has_bullets and plan_kw
    if not calls and not final:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No trajectory data', 'evidence_refs':[]}
    conf = 'medium'
    reason = f'early_calls={early_count}, bullets={len(bullets)}, plan_kw={plan_kw}'
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': reason, 'evidence_refs': []}
