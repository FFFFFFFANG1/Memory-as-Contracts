def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trace', 'evidence_refs': []}
    def is_fail(c):
        r = c.get('result')
        if r is None:
            return False
        s = str(r).lower()
        return any(k in s for k in ['error', 'failed', 'failure', 'exception', 'unavailable', 'not found', 'timeout'])
    # Group consecutive calls by tool name to identify retry sequences
    failures = [i for i, c in enumerate(calls) if is_fail(c)]
    if not failures:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool failures observed; constraint not triggered', 'evidence_refs': []}
    issues = []
    refs = []
    i = 0
    while i < len(calls):
        if is_fail(calls[i]):
            name = calls[i].get('name')
            # count consecutive same-tool retries after this failure
            j = i + 1
            retries = 0
            while j < len(calls) and calls[j].get('name') == name:
                retries += 1
                if not is_fail(calls[j]):
                    break
                j += 1
            # If all attempts failed including original, retries should be up to 3
            last_idx = i + retries
            all_failed = all(is_fail(calls[k]) for k in range(i, last_idx + 1))
            if all_failed:
                if retries > 3:
                    issues.append(f'Tool {name} retried {retries} times (>3) after failure at index {i}')
                    refs.append(i)
                elif retries < 3:
                    # only an issue if data was declared unavailable without exhausting retries
                    final = (trace.get('final_response') or '').lower()
                    if any(k in final for k in ['unavailable', 'could not', 'unable to', 'not available']):
                        pass  # acceptable if retries < 3 but tool eventually succeeded? here all_failed
                        issues.append(f'Tool {name} only retried {retries} times before giving up at index {i}')
                        refs.append(i)
            i = last_idx + 1
        else:
            i += 1
    if issues:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(issues), 'evidence_refs': refs}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Failures were followed by up to 3 retries of same tool', 'evidence_refs': failures}
