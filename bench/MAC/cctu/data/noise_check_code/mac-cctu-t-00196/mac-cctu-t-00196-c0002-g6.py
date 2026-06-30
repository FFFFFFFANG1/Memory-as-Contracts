def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found.', 'evidence_refs': []}
    calc_indices = [i for i, c in enumerate(calls) if c.get('name') == 'advanced_arithmetic_calculator']
    if not calc_indices:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'advanced_arithmetic_calculator was never invoked.', 'evidence_refs': []}
    first_calc_idx = calc_indices[0]
    first_call = calls[first_calc_idx]
    # Must be first tool call overall (no substantive numeric computation before)
    if first_calc_idx != 0:
        prior = [calls[i].get('name') for i in range(first_calc_idx)]
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Other tools called before sanity check: {prior}', 'evidence_refs': [{'index': i} for i in range(first_calc_idx)]}
    # Inspect arguments for triviality
    args = first_call.get('arguments', {}) or {}
    expr = ''
    if isinstance(args, dict):
        for k in ('expression', 'expr', 'input', 'query', 'problem'):
            v = args.get(k)
            if isinstance(v, str):
                expr = v
                break
        if not expr:
            # fallback: join all string values
            expr = ' '.join(str(v) for v in args.values() if isinstance(v, (str, int, float)))
    elif isinstance(args, str):
        expr = args
    expr_stripped = expr.strip()
    if not expr_stripped:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not extract expression from first calculator call.', 'evidence_refs': [{'index': 0}]}
    # Trivial heuristic: short, only digits/basic operators, small numbers
    trivial_pattern = re.fullmatch(r'\s*\d{1,3}\s*([+\-*/]\s*\d{1,3}\s*){0,3}', expr_stripped)
    is_short = len(expr_stripped) <= 20
    if trivial_pattern and is_short:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'First call is calculator with trivial expression: {expr_stripped!r}', 'evidence_refs': [{'index': 0, 'expression': expr_stripped}]}
    if is_short and re.fullmatch(r'[\d\s+\-*/().]+', expr_stripped):
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'First call is calculator with simple expression: {expr_stripped!r}', 'evidence_refs': [{'index': 0, 'expression': expr_stripped}]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'First calculator expression does not look like a trivial sanity check: {expr_stripped!r}', 'evidence_refs': [{'index': 0, 'expression': expr_stripped}]}
