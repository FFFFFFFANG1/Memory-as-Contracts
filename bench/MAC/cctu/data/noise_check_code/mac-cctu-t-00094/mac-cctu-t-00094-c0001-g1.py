def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response found.', 'evidence_refs': []}
    prefix_ok = resp.startswith('Supply chain summary:')
    if not prefix_ok:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Response does not begin with the required prefix.', 'evidence_refs': [resp[:80]]}
    # Check for enumeration of supplier tiers (semantic-ish heuristic).
    tier_mentions = re.findall(r'(?i)tier\s*\d+|tier\s+(?:one|two|three|four|five)', resp)
    if len(tier_mentions) >= 1:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Prefix present and {len(tier_mentions)} tier mention(s) detected.', 'evidence_refs': tier_mentions[:5]}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Prefix present but no explicit tier enumeration detected; cannot confirm completeness of tiers identified during the audit.', 'evidence_refs': [resp[:120]]}
