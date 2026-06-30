def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    step_pattern = re.compile(r'(?mi)^\s*step\s*\d+\s*[:.)-]')
    phase_pattern = re.compile(r'(?m)Phase-\d+\s*>>')
    has_step = bool(step_pattern.search(text))
    has_phase = bool(phase_pattern.search(text))
    if has_step:
        return {'observed_followed': False, 'confidence':'high','reason':'Found Step X: notation in final response','evidence_refs':[step_pattern.search(text).group(0)]}
    if has_phase:
        return {'observed_followed': True, 'confidence':'high','reason':'Final response uses Phase-N >> prefix','evidence_refs':[phase_pattern.search(text).group(0)]}
    return {'observed_followed': None, 'confidence':'low','reason':'No explicit step or Phase-N labels detected; cannot confirm reasoning step labeling','evidence_refs':[]}
