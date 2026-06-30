def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    source_ids = set()
    evidence = []
    id_keys = ('source_id', 'sourceId', 'source', 'identifier', 'id', 'ref', 'reference', 'source_ref')
    def extract(obj):
        found = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                if any(k.lower() == ik.lower() for ik in id_keys) and isinstance(v, (str, int)):
                    found.add(str(v))
                else:
                    found |= extract(v)
        elif isinstance(obj, list):
            for it in obj:
                found |= extract(it)
        elif isinstance(obj, str):
            for m in re.findall(r'(?:source[_-]?id|src[_-]?id|ref)["\':= ]+([A-Za-z0-9_\-]+)', obj, re.I):
                found.add(m)
        return found
    for i, tc in enumerate(tool_calls):
        res = tc.get('result')
        ids = extract(res)
        if ids:
            source_ids |= ids
            evidence.append({'index': i, 'tool': tc.get('name'), 'ids': list(ids)[:5]})
    if len(source_ids) >= 3:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Found {len(source_ids)} distinct source identifiers across tool results', 'evidence_refs': evidence}
    if len(source_ids) == 0:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No source identifiers detectable in tool results', 'evidence_refs': evidence}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(source_ids)} distinct source identifiers cross-checked (need >=3)', 'evidence_refs': evidence}
