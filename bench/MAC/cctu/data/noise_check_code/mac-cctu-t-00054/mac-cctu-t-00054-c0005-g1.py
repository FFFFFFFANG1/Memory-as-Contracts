def evaluate(trace):
    import re
    tcs = trace.get('tool_calls', []) or []
    pf_calls = [t for t in tcs if (t.get('name') or '') == 'paleontologist_discovery_finder']
    n = len(pf_calls)
    final = trace.get('final_response') or ''
    md_patterns = [r'^#{1,6}\s', r'\*\*[^*]+\*\*', r'(^|\s)\*[^*]+\*', r'`[^`]+`', r'^\s*[-*+]\s', r'^\s*\d+\.\s', r'\[[^\]]+\]\([^)]+\)', r'^>\s']
    has_md = any(re.search(p, final, re.MULTILINE) for p in md_patterns)
    stripped = final.strip()
    # single sentence check: one terminal punctuation at end, no internal sentence breaks
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', stripped)
    single_sentence = len([s for s in sentences if s.strip()]) <= 1
    tool_ok = n <= 3
    fmt_ok = (not has_md) and single_sentence and bool(stripped)
    followed = tool_ok and fmt_ok
    reason = f'pf_calls={n} (<=3:{tool_ok}); has_md={has_md}; single_sentence={single_sentence}'
    return {'observed_followed': followed, 'confidence': 'high' if stripped else 'low', 'reason': reason, 'evidence_refs': []}
