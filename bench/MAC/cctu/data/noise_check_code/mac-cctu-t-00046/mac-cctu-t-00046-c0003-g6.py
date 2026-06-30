def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    used = [tc.get('name') for tc in tool_calls]
    non_allowed = [n for n in used if n and n != 'election_result_finder']
    if used and non_allowed:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'used non-allowed tools: {non_allowed}', 'evidence_refs': non_allowed}
    if not used:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no tool calls observed; cannot confirm exclusive use', 'evidence_refs': []}
    # Check if multiple contested seats appear on separate lines
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    # Heuristic: look for 'seat' mentions
    seat_mentions = re.findall(r'(?i)seat|constituency|district|riding', final)
    if len(seat_mentions) <= 1:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'single or no seat reference; line separation not testable', 'evidence_refs': []}
    # Count lines containing seat-like tokens
    seat_lines = [l for l in lines if re.search(r'(?i)seat|constituency|district|riding', l)]
    if len(seat_lines) >= 2:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'multiple seat references appear on separate lines', 'evidence_refs': seat_lines[:3]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'multiple seats mentioned but not on separate lines', 'evidence_refs': [final[:200]]}
