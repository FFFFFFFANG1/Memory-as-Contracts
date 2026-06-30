def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    if not traj:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no trajectory','evidence_refs':[]}
    first = traj[0]
    content = (first.get('content') or '').strip()
    tool_calls = first.get('tool_calls') or []
    if tool_calls:
        return {'observed_followed': False,'confidence':'high','reason':'triage step invoked tools','evidence_refs':['trajectory[0].tool_calls']}
    if not content:
        return {'observed_followed': None,'confidence':'low','reason':'triage step has no content','evidence_refs':[]}
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    bullet_re = re.compile(r'^([-*+•]|\d+[.)])\s+')
    bullets = [l for l in lines if bullet_re.match(l)]
    if len(bullets) < 2 or len(bullets) < max(1, len(lines) - 1):
        return {'observed_followed': False,'confidence':'medium','reason':'triage content is not a short bullet list','evidence_refs':['trajectory[0].content']}
    if len(bullets) > 12:
        return {'observed_followed': False,'confidence':'medium','reason':'bullet list not short','evidence_refs':['trajectory[0].content']}
    low = content.lower()
    answer_markers = ['final answer','answer:','in conclusion','therefore the answer','the answer is']
    if any(m in low for m in answer_markers):
        return {'observed_followed': False,'confidence':'medium','reason':'triage step contains a final answer','evidence_refs':['trajectory[0].content']}
    return {'observed_followed': True,'confidence':'medium','reason':'triage step is a short bullet list with no tools and no final answer','evidence_refs':['trajectory[0]']}
