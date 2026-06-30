def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    low = final.lower()
    step_patterns = [r'step\s*\d+', r'\bstep\s+one\b', r'\bstep\s+two\b', r'^\s*\d+[\.\)]\s+', r'\bfirst[,:]', r'\bsecond[,:]', r'\bthen[,:]', r'\bnext[,:]', r'\bfinally[,:]']
    hits = 0
    for p in step_patterns:
        if re.search(p, low, re.MULTILINE):
            hits += 1
    reasoning_markers = ['reasoning', 'rationale', 'explanation', 'because', 'therefore', 'thus', 'analysis']
    rm_hits = sum(1 for m in reasoning_markers if m in low)
    numbered = len(re.findall(r'^\s*\d+[\.\)]\s+', final, re.MULTILINE))
    has_steps = hits >= 2 or numbered >= 2
    has_reasoning = rm_hits >= 1 or has_steps
    has_answer = len(final.strip()) > 40
    followed = has_steps and has_reasoning and has_answer
    return {'observed_followed': bool(followed), 'confidence':'medium','reason': f'step_hits={hits}, numbered={numbered}, reasoning_markers={rm_hits}, has_answer={has_answer}','evidence_refs':[]}
