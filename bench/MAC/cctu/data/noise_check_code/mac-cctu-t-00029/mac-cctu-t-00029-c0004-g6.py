def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = text.lower()
    mentions_eu = ('eu' in low or 'european union' in low) and ('turnout' in low) and ('average' in low or 'avg' in low or 'mean' in low)
    bullet_lines = [l.strip() for l in text.splitlines() if re.match(r'^\s*([-*+•]|\d+[\.)])\s+', l)]
    states = ['austria','belgium','bulgaria','croatia','cyprus','czech','denmark','estonia','finland','france','germany','greece','hungary','ireland','italy','latvia','lithuania','luxembourg','malta','netherlands','poland','portugal','romania','slovakia','slovenia','spain','sweden']
    bullet_states = set()
    for b in bullet_lines:
        bl = b.lower()
        for s in states:
            if s in bl:
                bullet_states.add(s)
    has_list = len(bullet_lines) >= 3 and len(bullet_states) >= 3
    followed = bool(mentions_eu and has_list)
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': f'eu_avg_mention={mentions_eu}, bullet_states={sorted(bullet_states)}, bullets={len(bullet_lines)}', 'evidence_refs': []}
