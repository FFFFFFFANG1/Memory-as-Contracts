import re
def evaluate(trace):
    text = trace.get('final_response','') or ''
    tool_calls = trace.get('tool_calls', []) or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to evaluate facts against.', 'evidence_refs': []}
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Empty final response.', 'evidence_refs': []}
    has_percent = bool(re.search(r'\d+(?:\.\d+)?\s*%', text))
    latency_pattern = re.compile(r'(latency|elapsed|duration|took|response time|ms\b|seconds?\b|\bs\b)', re.IGNORECASE)
    has_latency = bool(latency_pattern.search(text))
    has_time_value = bool(re.search(r'\d+(?:\.\d+)?\s*(ms|s|sec|seconds|milliseconds)\b', text, re.IGNORECASE))
    if has_percent and has_latency and has_time_value:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Final response contains percentage confidence and latency values.', 'evidence_refs': []}
    missing = []
    if not has_percent: missing.append('confidence percentage')
    if not (has_latency and has_time_value): missing.append('tool latency value')
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing: ' + ', '.join(missing), 'evidence_refs': []}
