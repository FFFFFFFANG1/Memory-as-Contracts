def evaluate(trace):
    import re
    tools = ['artwork_fame_analyzer','biographical_info_finder','explorer_discovery_finder','geographical_feature_analyzer','historical_figure_info','historical_infrastructure_designer_finder','historical_residence_locator','population_estimator','railway_connection_finder','river_length_calculator']
    texts = []
    fr = trace.get('final_response') or ''
    if fr: texts.append(fr)
    for step in trace.get('trajectory', []) or []:
        c = step.get('content') if isinstance(step, dict) else None
        if c: texts.append(c)
    bullet_re = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)])\s+(.*)$')
    found_enum = False
    violations = []
    for text in texts:
        lines = text.splitlines()
        # find contiguous bullet blocks
        i = 0
        while i < len(lines):
            if bullet_re.match(lines[i]):
                block = []
                while i < len(lines) and (bullet_re.match(lines[i]) or lines[i].strip()==''):
                    block.append(lines[i])
                    i += 1
                # check if block references tools (looks like sub-task enum)
                bullets = [bullet_re.match(l).group(1).strip() for l in block if bullet_re.match(l)]
                tool_hits = sum(1 for b in bullets if any(t in b for t in tools))
                if tool_hits >= 2:
                    found_enum = True
                    # ensure no prose lines between bullets
                    non_bullet_between = False
                    seen_bullet = False
                    for l in block:
                        if bullet_re.match(l):
                            seen_bullet = True
                        elif l.strip() and seen_bullet:
                            non_bullet_between = True
                    if non_bullet_between:
                        violations.append('prose between bullets')
                    # each bullet must be exactly one tool name (allow minor punctuation)
                    for b in bullets:
                        stripped = re.sub(r'[`*_().,:;]', '', b).strip()
                        matched_tools = [t for t in tools if t in b]
                        if len(matched_tools) != 1:
                            violations.append(f'bullet has {len(matched_tools)} tool names: {b!r}')
                        elif stripped != matched_tools[0] and not re.fullmatch(re.escape(matched_tools[0])+r'[\s\-:].{0,40}', stripped):
                            # allow only tool name (possibly with backticks); reject if extra prose
                            if stripped != matched_tools[0]:
                                violations.append(f'extra prose in bullet: {b!r}')
            else:
                i += 1
    if not found_enum:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no sub-task enumeration list detected', 'evidence_refs': []}
    if violations:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(violations[:3]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'bulleted list with one tool per bullet, no prose between', 'evidence_refs': []}
