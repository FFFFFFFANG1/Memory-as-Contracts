def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    linguistic = {'language_speaker_estimator', 'global_language_statistics_v2'}
    used_linguistic = [tc.get('name') for tc in tool_calls if tc.get('name') in linguistic]
    final = trace.get('final_response') or ''
    if not tool_calls and not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no evidence', 'evidence_refs': []}
    # Check: only language_speaker_estimator used among linguistic tools
    forbidden_used = [n for n in used_linguistic if n != 'language_speaker_estimator']
    if forbidden_used:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'used non-preferred linguistic tool(s): {forbidden_used}', 'evidence_refs': []}
    # Check single linguistic tool per query (no duplicates beyond one call ideally; allow multiple calls of same tool)
    # Check plain-text bulleted list in final response
    if final.strip():
        lines = [ln for ln in final.splitlines() if ln.strip()]
        bullet_lines = [ln for ln in lines if re.match(r'^\s*[-*\u2022]\s+', ln)]
        has_bullets = len(bullet_lines) >= 1 and len(bullet_lines) >= max(1, len(lines)//2)
        # plain text: no markdown bold/italic/headers/code
        has_md = bool(re.search(r'(\*\*|__|^#+\s|```|\[[^\]]+\]\([^)]+\))', final, re.MULTILINE))
        if not has_bullets:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final response is not a bulleted list', 'evidence_refs': []}
        if has_md:
            return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final response contains markdown formatting beyond bullets', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'only language_speaker_estimator used among linguistic tools and output is plain-text bullets', 'evidence_refs': []}
