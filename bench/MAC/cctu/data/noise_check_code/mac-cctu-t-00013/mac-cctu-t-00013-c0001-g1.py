def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    tool_calls = trace.get('tool_calls') or []
    allowed = {'historical_event_finder','event_information_retriever'}
    used = [tc for tc in tool_calls if tc.get('name') in allowed]
    # Look for findings followed by bullet list
    lines = final.split('\n')
    bullets = [l for l in lines if re.match(r'^\s*[-*+]\s+', l)]
    has_findings = bool(re.search(r'finding|confirm|corroborat|cited', final, re.I))
    if not has_findings:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No findings detected in response to evaluate.', 'evidence_refs': []}
    if len(bullets) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Findings present but fewer than 2 bullets ({len(bullets)}) for corroboration.', 'evidence_refs': []}
    if len(used) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Only {len(used)} calls to historical_event_finder/event_information_retriever; need >=2 corroborating outputs.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Findings accompanied by >=2 bullets and >=2 corroborating tool outputs from allowed tools.', 'evidence_refs': []}
