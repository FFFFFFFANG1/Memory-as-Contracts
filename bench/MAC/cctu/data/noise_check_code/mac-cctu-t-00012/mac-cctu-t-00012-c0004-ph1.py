def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    # Find market impact estimate mention
    mi_patterns = [r'market[- ]impact', r'market impact estimate', r'preliminary.*impact', r'impact estimate']
    mi_pos = None
    for p in mi_patterns:
        m = re.search(p, low)
        if m:
            mi_pos = m.start() if mi_pos is None else min(mi_pos, m.start())
    # Find stakeholders mention
    sh_match = re.search(r'stakeholder', low)
    sh_pos = sh_match.start() if sh_match else None
    # Find closing date mention
    cd_patterns = [r'closing date', r'close date', r'closes on', r'closing on']
    cd_pos = None
    for p in cd_patterns:
        m = re.search(p, low)
        if m:
            cd_pos = m.start() if cd_pos is None else min(cd_pos, m.start())
    if cd_pos is None:
        # No closing date reported; constraint vacuously satisfied if mi and sh present or not required
        if mi_pos is not None and sh_pos is not None:
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'market impact and stakeholders present; no closing date reported', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no closing date reported and missing market-impact or stakeholders; constraint may be vacuous', 'evidence_refs': []}
    # Closing date is present; require mi and sh to appear before it
    if mi_pos is None or sh_pos is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'closing date reported without preceding market-impact estimate and/or stakeholder list', 'evidence_refs': []}
    if mi_pos < cd_pos and sh_pos < cd_pos:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'market-impact and stakeholders mentioned before closing date', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'market-impact or stakeholders appeared after closing date', 'evidence_refs': []}
