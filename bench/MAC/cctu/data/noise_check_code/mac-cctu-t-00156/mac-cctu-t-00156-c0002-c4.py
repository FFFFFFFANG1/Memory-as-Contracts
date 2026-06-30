def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trace', 'evidence_refs': []}
    first = calls[0]
    first_name = first.get('name') or first.get('tool_name') or ''
    if first_name != 'polymath_identifier':
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'First tool call was {first_name!r}, not polymath_identifier', 'evidence_refs': [{'index': first.get('index', 0), 'name': first_name}]}
    # Gather fields from polymath_identifier outputs
    fields = []
    for c in calls:
        if (c.get('name') or c.get('tool_name')) != 'polymath_identifier':
            continue
        res = c.get('result')
        if res is None:
            continue
        if isinstance(res, dict):
            for k in ('fields', 'fields_of_accomplishment', 'disciplines', 'domains', 'areas'):
                v = res.get(k)
                if isinstance(v, list):
                    fields.extend([str(x) for x in v])
                elif isinstance(v, str):
                    fields.extend([s.strip() for s in re.split(r'[,;]', v) if s.strip()])
        elif isinstance(res, str):
            fields.extend([s.strip() for s in re.split(r'[,;\n]', res) if s.strip()])
    final = trace.get('final_response') or ''
    if not final:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No final response to inspect for cited fields', 'evidence_refs': []}
    low = final.lower()
    cited = set()
    for f in fields:
        token = f.strip().lower()
        if len(token) < 3:
            continue
        if token in low:
            cited.add(token)
    if len(cited) >= 3:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'polymath_identifier called first; final cites {len(cited)} fields from its output: {sorted(cited)}', 'evidence_refs': [{'first_tool': first_name, 'cited_fields': sorted(cited)}]}
    if not fields:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'polymath_identifier called first but no fields parsable from its output', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(cited)} field(s) from polymath_identifier output cited in final response: {sorted(cited)}', 'evidence_refs': [{'available_fields': fields, 'cited': sorted(cited)}]}
