def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    low = text.lower()
    has_acquirer = any(t in low for t in ['acquirer', 'acquirers', 'buyer', 'bidder'])
    has_target = any(t in low for t in ['target compan', 'target:', 'targets'])
    has_rationale = any(t in low for t in ['rationale', 'reason for', 'included because', 'excluded because', 'inclusion', 'exclusion'])
    # Look for enumeration markers (lists)
    has_list = bool(re.search(r'(^|\n)\s*([-*\u2022]|\d+[.)])\s+', text))
    score = sum([has_acquirer, has_target, has_rationale, has_list])
    if score >= 4:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Response enumerates acquirers and targets with rationale.', 'evidence_refs': []}
    if score <= 1:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Response lacks enumeration of acquirers/targets with rationale.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': f'Partial signals only (score={score}): acquirer={has_acquirer}, target={has_target}, rationale={has_rationale}, list={has_list}.', 'evidence_refs': []}
