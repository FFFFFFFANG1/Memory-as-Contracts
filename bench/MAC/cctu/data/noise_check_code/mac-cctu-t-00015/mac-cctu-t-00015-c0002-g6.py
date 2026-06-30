def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '')
    text_parts = [final]
    for step in trace.get('trajectory') or []:
        c = step.get('content')
        if isinstance(c, str):
            text_parts.append(c)
    blob = ' '.join(text_parts).lower()
    royal_terms = ['royal','royalty','king','queen','prince','princess','duke','duchess','monarch','crown','sultan','emir','tsar','czar','emperor','empress','heir apparent','house of windsor','house of saud']
    royal_hit = any(t in blob for t in royal_terms)
    for call in calls:
        args = call.get('arguments') or {}
        if isinstance(args, dict):
            ablob = ' '.join(str(v).lower() for v in args.values())
            if any(t in ablob for t in royal_terms):
                royal_hit = True
                break
    if not royal_hit:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No indication the event involves a royal household; constraint not triggered by observable evidence.', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    if not names:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Royal context detected but no tool calls were made.', 'evidence_refs': []}
    primary = names[0]
    used_aviation = 'aviation_incident_info_retriever' in names
    if primary == 'aviation_incident_info_retriever':
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Aviation incident retriever invoked first as primary source.', 'evidence_refs': [{'tool_index': 0, 'tool': primary}]}
    if used_aviation:
        idx = names.index('aviation_incident_info_retriever')
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Aviation incident retriever used but not primary (first tool was {primary}).', 'evidence_refs': [{'first_tool': primary, 'aviation_index': idx}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'Royal-related event but aviation_incident_info_retriever was never used.', 'evidence_refs': [{'tools_used': names}]}
