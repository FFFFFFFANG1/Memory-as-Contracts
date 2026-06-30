def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    has_structured = bool(re.search(r'[\{\[]', resp)) or bool(re.search(r'^\s*[-*|#]', resp, re.M)) or '|' in resp
    lines = [l for l in resp.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Empty response', 'evidence_refs': []}
    tail = '\n'.join(lines[-6:]).lower()
    mentions_tools = any(k in tail for k in ['tool observation', 'tool-derived', 'from tool', 'tool output', 'tools', 'tool call', 'observed via tool', 'retrieved via tool'])
    mentions_figures = any(k in tail for k in ['figure', 'data', 'number', 'value', 'statistic', 'information'])
    disclaimer_like = any(k in tail for k in ['disclaimer', 'note:', 'all figures', 'all data', 'originate', 'sourced', 'derived solely', 'solely from'])
    last_line = lines[-1].strip()
    plain = not re.match(r'^[\{\[\|#\-\*`]', last_line) and '|' not in last_line
    followed = bool(disclaimer_like and mentions_tools and plain)
    if not has_structured and not followed:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No structured output detected; disclaimer requirement ambiguous', 'evidence_refs': []}
    reason = 'Disclaimer paragraph present mentioning tool observations' if followed else 'Missing plain-text disclaimer that figures come solely from tool observations'
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': reason, 'evidence_refs': [tail[:200]]}
