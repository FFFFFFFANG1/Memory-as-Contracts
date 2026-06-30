def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    low = text.lower()
    deal_terms = ['deal clos','merger clos','acquisition clos','transaction clos']
    is_deal_closure = any(t in low for t in deal_terms)
    if not is_deal_closure:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No deal closure report context detected in final response.', 'evidence_refs': []}
    has_divestiture = 'divest' in low
    antitrust_terms = ['antitrust','competition authority','regulator','ftc','doj','european commission','cma','sambv','kfst']
    has_antitrust = any(t in low for t in antitrust_terms)
    jurisdiction_terms = ['jurisdiction','united states','u.s.','eu','european union','uk','china','japan','germany','france','brazil','india','canada','australia']
    juris_hits = sum(1 for t in jurisdiction_terms if t in low)
    if has_divestiture and has_antitrust and juris_hits >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Divestiture conditions enumerated across multiple jurisdictions with antitrust framing.', 'evidence_refs': []}
    if not has_divestiture or not has_antitrust:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing divestiture or antitrust regulator references in deal closure report.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': 'Divestiture/antitrust mentioned but jurisdictions not enumerated.', 'evidence_refs': []}
