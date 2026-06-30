def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    names = [c.get('name') for c in calls]
    has_retriever = 'historical_event_data_retriever' in names
    has_finder = 'historical_event_finder' in names
    if not (has_retriever and has_finder):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Both historical_event_data_retriever and historical_event_finder must be called for cross-checking.', 'evidence_refs': [{'type':'tool_names','value':names}]}
    def norm(x):
        try:
            return re.sub(r'\s+',' ', str(x)).strip().lower()
        except Exception:
            return ''
    retr_results = [norm(c.get('result')) for c in calls if c.get('name')=='historical_event_data_retriever']
    find_results = [norm(c.get('result')) for c in calls if c.get('name')=='historical_event_finder']
    final = trace.get('final_response','') or ''
    flag_terms = ['inconsisten','discrepanc','conflict','differ','mismatch','contradict','disagree','no inconsisten','consistent','corroborat','cross-check','cross check','agree']
    final_low = final.lower()
    mentions_crosscheck = any(t in final_low for t in flag_terms)
    if not mentions_crosscheck:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final report does not mention corroboration or any inconsistency between the two tools.', 'evidence_refs': [{'type':'final_response_excerpt','value':final[:400]}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Both tools were invoked and the final report addresses corroboration/inconsistency.', 'evidence_refs': [{'type':'tool_names','value':names}]}
