def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not final and not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no evidence','evidence_refs':[]}
    if tool_calls:
        return {'observed_followed': False, 'confidence':'high','reason':f'tool calls made before clarification: {len(tool_calls)}','evidence_refs':[{'type':'tool_calls','count':len(tool_calls)}]}
    # Count sentences via terminal punctuation
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', final) if s.strip()]
    if len(sentences) > 1:
        return {'observed_followed': False, 'confidence':'medium','reason':f'response has {len(sentences)} sentences, not a single brief acknowledgement','evidence_refs':[{'type':'final_response','sentences':len(sentences)}]}
    if len(final.split()) > 60:
        return {'observed_followed': False, 'confidence':'medium','reason':'response not brief','evidence_refs':[{'type':'final_response','words':len(final.split())}]}
    return {'observed_followed': True, 'confidence':'high','reason':'single brief sentence and no tool calls','evidence_refs':[{'type':'final_response','words':len(final.split())}]}
