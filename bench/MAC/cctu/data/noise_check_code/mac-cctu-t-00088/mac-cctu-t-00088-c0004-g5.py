def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    sc_calls = [c for c in calls if c.get('name') == 'supply_chain_tracker']
    if not sc_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'supply_chain_tracker was not invoked', 'evidence_refs': []}
    final = trace.get('final_response') or ''
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response to check verbatim citation', 'evidence_refs': []}
    def extract_snippets(result):
        if result is None:
            return []
        if isinstance(result, str):
            return [result]
        if isinstance(result, dict):
            out = []
            for v in result.values():
                out.extend(extract_snippets(v))
            return out
        if isinstance(result, list):
            out = []
            for v in result:
                out.extend(extract_snippets(v))
            return out
        return [str(result)]
    snippets = []
    for c in sc_calls:
        snippets.extend(extract_snippets(c.get('result')))
    snippets = [s for s in snippets if isinstance(s, str) and len(s.strip()) >= 3]
    if not snippets:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'supply_chain_tracker produced no inspectable output', 'evidence_refs': []}
    cited = False
    for s in snippets:
        s_clean = s.strip()
        if len(s_clean) <= 200:
            if s_clean in final:
                cited = True
                break
        else:
            # check substantial substrings
            for chunk_size in (120, 80, 50):
                for i in range(0, max(1, len(s_clean) - chunk_size + 1), chunk_size):
                    chunk = s_clean[i:i+chunk_size]
                    if chunk in final:
                        cited = True
                        break
                if cited:
                    break
        if cited:
            break
    if cited:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'supply_chain_tracker invoked and output appears cited verbatim', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'supply_chain_tracker invoked but output not cited verbatim in final response', 'evidence_refs': []}
