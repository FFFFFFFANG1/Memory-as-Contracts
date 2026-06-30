def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text_parts = []
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            if content:
                pre_text_parts.append(content)
            break
        if content:
            pre_text_parts.append(content)
    if not found_tool:
        # no tool used; check final_response or any assistant content
        pre_text_parts.append(trace.get('final_response') or '')
    text = '\n'.join(pre_text_parts)
    if not text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool roadmap text found','evidence_refs':[]}
    # numbered roadmap: at least two numbered items like '1.' '2.'
    nums = re.findall(r'(?m)^\s*(\d+)[\.\)]\s+\S', text)
    has_roadmap = len(set(nums)) >= 2 and '1' in nums
    dep_terms = ['depend','dependenc','prerequisite','requires','before','after','order','sequence']
    has_deps = any(t in text.lower() for t in dep_terms)
    followed = has_roadmap and has_deps
    reason = f'numbered_items={sorted(set(nums))}, deps_mentioned={has_deps}'
    return {'observed_followed': bool(followed), 'confidence':'medium','reason':reason,'evidence_refs':[]}
