def evaluate(trace):
    import re
    tools = trace.get('tool_calls', []) or []
    targeted = [c for c in tools if c.get('name') in ('highway_length_calculator','historical_infrastructure_info')]
    if not targeted:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No relevant tool calls found.', 'evidence_refs': []}
    us_terms = ['united states','usa','u.s.','u.s.a','america','american']
    non_us_hints = ['china','india','japan','france','germany','italy','spain','uk','united kingdom','england','russia','canada','mexico','brazil','australia','egypt','korea','africa','europe','asia']
    evidence = []
    bad = False
    unknown = False
    for c in targeted:
        args = c.get('arguments', {}) or {}
        text = json.dumps(args).lower() if not isinstance(args, str) else args.lower()
        result_text = json.dumps(c.get('result','')).lower() if not isinstance(c.get('result',''), str) else str(c.get('result','')).lower()
        has_us = any(t in text for t in us_terms)
        has_non_us = any(t in text for t in non_us_hints)
        if has_non_us and not has_us:
            bad = True
            evidence.append({'tool': c.get('name'), 'arguments': args, 'issue': 'non-US target'})
        elif not has_us and not has_non_us:
            unknown = True
            evidence.append({'tool': c.get('name'), 'arguments': args, 'issue': 'target country unclear'})
        else:
            evidence.append({'tool': c.get('name'), 'arguments': args, 'ok': True})
    final = (trace.get('final_response') or '').lower()
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Restricted tool used on non-US target.', 'evidence_refs': evidence}
    if unknown:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not confirm US-only targeting from arguments.', 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All restricted tool calls targeted US.', 'evidence_refs': evidence}
