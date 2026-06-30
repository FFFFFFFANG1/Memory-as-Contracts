def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    content = (first.get('content') or '').strip()
    tool_calls_first = first.get('tool_calls') or []
    if tool_calls_first:
        return {'observed_followed': False, 'confidence':'high','reason':'tool call issued in first step before confirmation','evidence_refs':['trajectory[0].tool_calls']}
    if not content:
        return {'observed_followed': False, 'confidence':'medium','reason':'first step has no message content','evidence_refs':['trajectory[0]']}
    low = content.lower()
    greet_terms = ['hello','hi ','hi,','hi!','hey','greetings','good morning','good afternoon','good evening','welcome']
    has_greet = any(t in low for t in greet_terms)
    confirm_terms = ['confirm','correct?','is that right','is this correct','scope','proceed','shall i','should i','before i proceed','before proceeding','please confirm','can you confirm']
    has_confirm = any(t in low for t in confirm_terms)
    # restate verbatim: we cannot verify exact wording without the original objective; check for quoting style
    has_restate = bool(re.search(r'"[^"]{10,}"', content)) or bool(re.search(r"'[^']{10,}'", content)) or ('objective' in low) or ('you asked' in low) or ('you said' in low) or ('your request' in low)
    missing = []
    if not has_greet: missing.append('greeting')
    if not has_restate: missing.append('restated objective')
    if not has_confirm: missing.append('confirmation request')
    if missing:
        return {'observed_followed': False, 'confidence':'medium','reason':'missing: '+', '.join(missing),'evidence_refs':['trajectory[0].content']}
    return {'observed_followed': True, 'confidence':'medium','reason':'greeted, restated, requested confirmation before any tool call','evidence_refs':['trajectory[0].content']}
