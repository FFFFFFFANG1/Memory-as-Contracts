def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    count = sum(1 for c in tool_calls if (c.get('name') or '') == 'election_result_retriever')
    final = trace.get('final_response') or ''
    lines = [ln.strip() for ln in final.splitlines() if ln.strip()]
    numbered = [ln for ln in lines if re.match(r'^\(?\d+[\.\)]\s+', ln)]
    bullets_ok = len(numbered) >= 5
    tool_ok = count >= 3
    followed = bool(tool_ok and bullets_ok)
    return {
        'observed_followed': followed,
        'confidence': 'high',
        'reason': f'election_result_retriever calls={count} (need>=3); numbered items={len(numbered)} (need>=5)',
        'evidence_refs': []
    }
