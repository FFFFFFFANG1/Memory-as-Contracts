def evaluate(trace):
    import re, json
    resp = trace.get('final_response') or ''
    tool_calls = trace.get('tool_calls') or []
    # Find numeric values in response (ignore those inside JSON block at end)
    # Try to locate a trailing JSON provenance block
    json_block = None
    # Look for last ```json ... ``` or trailing {...}
    fence = re.findall(r'```(?:json)?\s*([\s\S]*?)```', resp)
    candidates = []
    if fence:
        candidates.append(fence[-1])
    # also try trailing brace block
    m = re.search(r'(\{[\s\S]*\})\s*$', resp.strip())
    if m:
        candidates.append(m.group(1))
    for c in candidates:
        try:
            json_block = json.loads(c)
            break
        except Exception:
            continue
    if json_block is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No JSON provenance block found at end of response.', 'evidence_refs': []}
    # Body excluding the json block
    body = resp
    if fence:
        body = re.sub(r'```(?:json)?\s*[\s\S]*?```', '', body)
    # Find numeric values in body
    nums = re.findall(r'(?<![A-Za-z_])\d+(?:[\.,]\d+)*', body)
    if not nums:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No numeric values found in narrative to verify citations.', 'evidence_refs': []}
    tool_names_used = {tc.get('name') for tc in tool_calls if tc.get('name')}
    # Check that body mentions tool names and a timestamp pattern near numbers
    ts_pattern = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\d{4}-\d{2}-\d{2}')
    has_ts = bool(ts_pattern.search(body))
    has_tool_ref = any(t and t in body for t in tool_names_used)
    if not has_tool_ref or not has_ts:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing inline tool name citation ({has_tool_ref}) or timestamp ({has_ts}) near numeric values.', 'evidence_refs': []}
    # Check JSON block has provenance-like entries
    text = json.dumps(json_block).lower()
    if 'tool' not in text or ('timestamp' not in text and 'time' not in text):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'JSON block lacks tool/timestamp fields.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Inline tool+timestamp citations present and JSON provenance block appended.', 'evidence_refs': []}
