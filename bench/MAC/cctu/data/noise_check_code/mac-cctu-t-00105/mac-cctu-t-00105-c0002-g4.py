def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    traj = trace.get('trajectory') or []
    # Collect numeric figures from tool results
    num_re = re.compile(r'\b\d[\d,]*(?:\.\d+)?\b')
    figures_per_tool = []
    for tc in tool_calls:
        name = tc.get('name') or ''
        res = tc.get('result')
        text = res if isinstance(res, str) else (str(res) if res is not None else '')
        nums = set()
        for m in num_re.findall(text):
            s = m.replace(',', '')
            try:
                v = float(s)
                if v != 0:
                    nums.add(round(v, 4))
            except Exception:
                pass
        if nums:
            figures_per_tool.append((name, nums))
    if not figures_per_tool:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No numeric figures from tools detected.', 'evidence_refs': []}
    # Identify which figures are cross-checked (appear in >=2 distinct tools)
    all_nums = {}
    for name, nums in figures_per_tool:
        for n in nums:
            all_nums.setdefault(n, set()).add(name)
    verified = {n for n, s in all_nums.items() if len(s) >= 2}
    unverified = [n for n in all_nums if n not in verified]
    log_text = final + '\n' + '\n'.join((s.get('content') or '') for s in traj if isinstance(s, dict))
    has_unconfirmed_label = 'unconfirmed' in log_text.lower()
    if not unverified:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All tool-produced figures appear in at least two independent tools.', 'evidence_refs': []}
    # There are unverified figures; constraint allows them if labeled 'unconfirmed'
    if has_unconfirmed_label:
        return {'observed_followed': True, 'confidence': 'low', 'reason': f'{len(unverified)} unverified figures present and log contains "unconfirmed" label.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(unverified)} numeric figures not cross-checked and no "unconfirmed" label found.', 'evidence_refs': [str(n) for n in list(unverified)[:5]]}
