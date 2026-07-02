# Copyright 2026 Junjie Ye
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import json
import re
from datetime import datetime
from func_timeout import func_set_timeout, FunctionTimedOut
from typing import Any, Dict, List, Iterator, Set

_DATETIME_MODULE_PATTERN = re.compile(
    r"\bdatetime\.(?:datetime|date|timedelta|time|timezone)\b"
)
_DATETIME_CLASS_PATTERN = re.compile(r"(?<!\.)datetime\.strptime\b")


def _datetime_binding_for_code(code: str) -> Dict[str, Any]:
    """Bind ``datetime`` the way each simulator expects (class vs module)."""
    if _DATETIME_MODULE_PATTERN.search(code):
        import datetime as datetime_module

        return {"datetime": datetime_module}
    if _DATETIME_CLASS_PATTERN.search(code):
        from datetime import datetime as datetime_class

        return {"datetime": datetime_class}
    return {}


def tool_exec_namespace(*, code: str = "") -> Dict[str, Any]:
    """Common stdlib names used by CCTU tool simulators without explicit imports."""
    import calendar
    import copy
    import decimal
    import functools
    import hashlib
    import itertools
    import math
    import operator
    import random
    import re as re_module
    import statistics
    import string
    import time
    import uuid
    from collections import Counter, OrderedDict, defaultdict

    namespace = {
        "json": json,
        "re": re_module,
        "math": math,
        "random": random,
        "time": time,
        "collections": __import__("collections"),
        "itertools": itertools,
        "functools": functools,
        "statistics": statistics,
        "decimal": decimal,
        "copy": copy,
        "string": string,
        "calendar": calendar,
        "operator": operator,
        "hashlib": hashlib,
        "uuid": uuid,
        "Counter": Counter,
        "defaultdict": defaultdict,
        "OrderedDict": OrderedDict,
    }
    namespace.update(_datetime_binding_for_code(code))
    return namespace


def iter_jsonl(path: str) -> Iterator[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            raw = line.rstrip("\n")
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as e:
                raise RuntimeError(
                    f"[JSONDecodeError] file={path}, line={lineno}, err={e}\nraw={raw!r}"
                )


def norm_id(x: Any) -> str:
    return "" if x is None else str(x)


_MONTH_NAME_TO_NUM = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_ISO_DATE_TOKEN_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*\.?\s*$")
_ISO_DATE_IN_TEXT_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_MONTH_FIRST_DATE_RE = re.compile(
    r"\b("
    + "|".join(sorted(_MONTH_NAME_TO_NUM, key=len, reverse=True))
    + r")\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_DAY_FIRST_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+("
    + "|".join(sorted(_MONTH_NAME_TO_NUM, key=len, reverse=True))
    + r")\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(
    r"\b("
    + "|".join(sorted(_MONTH_NAME_TO_NUM, key=len, reverse=True))
    + r"),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_YEAR_MONTH_RE = re.compile(
    r"\b(\d{4}),?\s+("
    + "|".join(sorted(_MONTH_NAME_TO_NUM, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)


def _month_num(name: str) -> int | None:
    return _MONTH_NAME_TO_NUM.get(str(name or "").strip().lower())


def _iso_date(year: int | str, month: int | str, day: int | str) -> str | None:
    try:
        parsed = datetime(int(year), int(month), int(day))
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d")


def normalize_date_token(token: str) -> str | None:
    """Normalize a single date token to ISO ``YYYY-MM-DD`` when possible."""
    cleaned = str(token or "").strip().rstrip(".")
    if not cleaned:
        return None

    iso_match = _ISO_DATE_TOKEN_RE.match(cleaned)
    if iso_match:
        return _iso_date(*iso_match.groups())

    month_first = _MONTH_FIRST_DATE_RE.match(cleaned)
    if month_first:
        month = _month_num(month_first.group(1))
        if month is not None:
            return _iso_date(month_first.group(3), month, month_first.group(2))

    day_first = _DAY_FIRST_DATE_RE.match(cleaned)
    if day_first:
        month = _month_num(day_first.group(2))
        if month is not None:
            return _iso_date(day_first.group(3), month, day_first.group(1))

    return None


def extract_normalized_dates(text: str) -> tuple[Set[str], Set[str]]:
    """Return full ISO dates and explicit year-month prefixes found in free text."""
    full_dates: Set[str] = set()
    explicit_year_months: Set[str] = set()
    body = str(text or "")

    for match in _ISO_DATE_IN_TEXT_RE.finditer(body):
        iso = _iso_date(*match.groups())
        if iso:
            full_dates.add(iso)

    for match in _MONTH_FIRST_DATE_RE.finditer(body):
        month = _month_num(match.group(1))
        if month is None:
            continue
        iso = _iso_date(match.group(3), month, match.group(2))
        if iso:
            full_dates.add(iso)

    for match in _DAY_FIRST_DATE_RE.finditer(body):
        month = _month_num(match.group(2))
        if month is None:
            continue
        iso = _iso_date(match.group(3), month, match.group(1))
        if iso:
            full_dates.add(iso)

    for match in _MONTH_YEAR_RE.finditer(body):
        month = _month_num(match.group(1))
        if month is None:
            continue
        explicit_year_months.add(f"{int(match.group(2)):04d}-{month:02d}")

    for match in _YEAR_MONTH_RE.finditer(body):
        month = _month_num(match.group(2))
        if month is None:
            continue
        explicit_year_months.add(f"{int(match.group(1)):04d}-{month:02d}")

    return full_dates, explicit_year_months


def _golden_date_matches_predict(
    golden_iso: str,
    predict_dates: Set[str],
    explicit_year_months: Set[str],
) -> bool:
    if golden_iso in predict_dates:
        return True
    return golden_iso[:7] in explicit_year_months


def _answer_verify_single_golden(predict: Any, golden: Any) -> bool:
    golden_items = str(golden).split(", ")

    if isinstance(predict, (dict, list)):
        predict_s = json.dumps(predict, ensure_ascii=False)
    else:
        predict_s = str(predict)

    predict_norm = predict_s.lower().replace(",", "").strip()
    predict_dates, explicit_year_months = extract_normalized_dates(predict_s)

    for item in golden_items:
        item_text = str(item).strip()
        golden_iso = normalize_date_token(item_text)
        if golden_iso is not None:
            if not _golden_date_matches_predict(golden_iso, predict_dates, explicit_year_months):
                return False
            continue

        item_norm = item_text.lower().replace(",", "").strip().rstrip(".")
        if item_norm not in predict_norm:
            return False
    return True


def answer_verify(predict: Any, golden: Any) -> bool:
    if golden is None:
        return False
    golden_s = str(golden).strip()
    if re.search(r"\s+or\s+", golden_s, flags=re.IGNORECASE):
        alternatives = re.split(r"\s+or\s+", golden_s, flags=re.IGNORECASE)
        return any(
            _answer_verify_single_golden(predict, alt.strip())
            for alt in alternatives
            if alt.strip()
        )
    return _answer_verify_single_golden(predict, golden_s)


def build_tool_call_id2name(messages: List[dict]) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in (msg.get("tool_calls") or []):
            tc_id = tc.get("id")
            fn = tc.get("function") or {}
            name = fn.get("name")
            if tc_id and name:
                m[str(tc_id)] = str(name)
    return m


@func_set_timeout(10)
def call_function(name, arguments, code, **kwargs):
    namespace = {"__builtins__": __builtins__, **tool_exec_namespace(code=code)}
    exec(code, namespace, namespace)

    if name in namespace:
        predict = namespace[name](**arguments, **kwargs)
    else:
        raise NameError(f"name {name} is not defined")
    if type(predict) == dict or type(predict) == list:
        predict = json.dumps(predict, ensure_ascii=False)
    elif type(predict) != str:
        predict = str(predict)
    return predict


def get_feedback_tools(args_feedback, tool_calls, codes, **kwargs):
    res = []
    for tool_call in tool_calls:
        try:
            tool_name = tool_call['function']['name']
            tool_args = json.loads(tool_call['function']['arguments'])
            code = codes[tool_name]
            has_fb = False
            for args_fb in args_feedback:
                if tool_call["id"] == args_fb["tool_call_id"]:
                    res.append(args_fb)
                    has_fb = True
                    continue
            if has_fb:
                continue

            feedback = call_function(
                tool_name, tool_args, code, **kwargs)

            res.append({"role": "tool", "content": feedback,
                       "tool_call_id": tool_call["id"]})
        except FunctionTimedOut as e:
            res.append(
                {"role": "tool", "content": f"an error occured when call {tool_call['function']['name']}: {str(e)}", "tool_call_id": tool_call["id"]})
        except Exception as e:
            res.append(
                {"role": "tool", "content": f"an error occured when call {tool_call['function']['name']}: {str(e)}", "tool_call_id": tool_call["id"]})

    return res
