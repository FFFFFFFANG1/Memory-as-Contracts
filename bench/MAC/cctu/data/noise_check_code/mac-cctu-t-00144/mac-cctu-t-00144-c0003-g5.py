def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    n = len(calls)
    final = (trace.get('final_response') or '').strip()
    if n > 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} tool calls; constraint allows at most one exploratory invocation.', 'evidence_refs': []}
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate hypothesis paragraph.', 'evidence_refs': []}
    hypothesis_markers = ['likely','perhaps','might','may','could','suggest','hypothes','approximat','estimate','presum','possibly','probably','seems','appears','around','roughly']
    has_hyp = any(m in final.lower() for m in hypothesis_markers)
    # Detect a definitive numerical answer: a standalone number presented as the answer
    definitive = bool(re.search(r'(?i)(the answer is|=\s*[-+]?\d|answer:\s*[-+]?\d|exactly\s+[-+]?\d)', final))
    if definitive and not has_hyp:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response presents a definitive numerical answer without hypothesis framing.', 'evidence_refs': []}
    if has_hyp and n <= 1:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'{n} tool call(s) and hypothesis-style language present.', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Could not clearly determine hypothesis framing vs definitive answer.', 'evidence_refs': []}
