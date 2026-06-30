def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    first_tool_idx = None
    pre_text = ''
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            first_tool_idx = i
            break
        pre_text += '\n' + (content or '')
    if first_tool_idx is None:
        # No tool calls happened; check if outline exists in final or trajectory text
        pre_text = (trace.get('final_response') or '') + '\n' + pre_text
        if not pre_text.strip():
            return {'observed_followed': None, 'confidence':'unknown','reason':'no content','evidence_refs':[]}
    text = pre_text.lower()
    if not text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'no pre-tool outline text','evidence_refs':[]}
    has_subtasks = bool(re.search(r'(sub[- ]?task|step\s*\d|task\s*\d|\b1[\.\)]\s|\n\s*[-*]\s)', text))
    has_tool = ('tool' in text) or any(t in text for t in ['element_information_provider','historical_event_info_combined','product_and_appliance_specification_retriever','smartphone_specification_retriever','universal_weight_calculator'])
    has_dep = bool(re.search(r'depend|requires|prerequisite|after\s+(step|task)|before\s+(step|task)|none\b', text))
    followed = has_subtasks and has_tool and has_dep
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': f'subtasks={has_subtasks}, tool={has_tool}, deps={has_dep}', 'evidence_refs': []}
