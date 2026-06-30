def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    names = [t.get('name') for t in tcs]
    final = trace.get('final_response') or ''
    required = {'election_result_retriever','election_result_analyzer'}
    used = required.intersection(names)
    retr_count = sum(1 for n in names if n in required)
    # find index of first non-required tool used as primary check: required tools should appear and dominate
    primary_ok = required.issubset(set(names))
    two_retrievals_before_answer = retr_count >= 2
    # Check numbered list format in final response
    lines = [ln for ln in final.splitlines() if ln.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence':'high','reason':'empty final response','evidence_refs':[]}
    numbered = [ln for ln in lines if re.match(r'^\s*\d+[\.\)]\s+', ln)]
    is_numbered_list = len(numbered) >= 2 and len(numbered) >= max(1, int(0.6*len(lines)))
    # No markdown emphasis: no **, __, *word*, _word_
    has_emphasis = bool(re.search(r'\*\*[^*]+\*\*', final) or re.search(r'__[^_]+__', final) or re.search(r'(?<!\*)\*[^*\n]+\*(?!\*)', final) or re.search(r'(?<!_)_[^_\n]+_(?!_)', final))
    ok = primary_ok and two_retrievals_before_answer and is_numbered_list and not has_emphasis
    reason = f'primary_tools_used={primary_ok}, retrievals={retr_count}, numbered_list={is_numbered_list}, has_emphasis={has_emphasis}'
    return {'observed_followed': bool(ok), 'confidence':'high' if (primary_ok and retr_count>0) else 'medium','reason': reason,'evidence_refs': []}
