def evaluate(trace):
    import re
    final=(trace.get('final_response') or '').strip()
    traj=trace.get('trajectory') or []
    tool_calls=trace.get('tool_calls') or []
    if not final:
        return {'observed_followed':None,'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Heuristic: a quick clarification exchange is a short final response that asks a question or is a brief acknowledgement
    q_like = final.endswith('?') or bool(re.match(r'^(could you|can you|do you|did you|are you|just to clarify|to clarify|which|what|when|where|who|how)\b', final.strip(), re.I))
    word_count = len(final.split())
    is_clarification = q_like and word_count <= 40
    if not is_clarification:
        return {'observed_followed':None,'confidence':'unknown','reason':'final response does not appear to be a quick clarification exchange','evidence_refs':[]}
    # Count sentences
    sentences=[s for s in re.split(r'(?<=[.!?])\s+', final) if s.strip()]
    single_sentence = len(sentences) <= 1
    has_tool_calls = len(tool_calls) > 0
    followed = single_sentence and not has_tool_calls
    reason=f'clarification detected; sentences={len(sentences)}, tool_calls={len(tool_calls)}'
    return {'observed_followed':bool(followed),'confidence':'medium','reason':reason,'evidence_refs':[]}
