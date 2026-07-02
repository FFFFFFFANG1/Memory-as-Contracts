from __future__ import annotations

from bench.MAC.cctu.bridge import import_cctu_attr

answer_verify = import_cctu_attr("utils.utils", "answer_verify")
normalize_date_token = import_cctu_attr("utils.utils", "normalize_date_token")


def test_normalize_date_token_iso_variants() -> None:
    assert normalize_date_token("2007-11-7") == "2007-11-07"
    assert normalize_date_token("2001-08-02.") == "2001-08-02"


def test_answer_verify_month_name_matches_iso_golden() -> None:
    assert answer_verify("September 17, 2001", "2001-9-17")
    assert answer_verify("**The answer is: ** **September 17, 2001**.", "2001-9-17")
    assert answer_verify("November 7, 2007", "2007-11-7")
    assert answer_verify("The date is May 10, 2007.", "2007-05-10")
    assert answer_verify("23 March 2007", "2007-3-23")


def test_answer_verify_iso_in_prose_matches_unpadded_golden() -> None:
    assert answer_verify("The conviction date is 2001-08-02.", "2001-8-2")


def test_answer_verify_month_year_matches_iso_golden() -> None:
    assert answer_verify("August, 2024", "2024-08-01")


def test_answer_verify_non_date_substring_still_works() -> None:
    assert answer_verify("Abdel Fattah el-Sisi", "Abdel Fattah el-Sisi.")
    assert answer_verify('{"president": "Abdel Fattah el-Sisi"}', "Abdel Fattah el-Sisi.")


def test_answer_verify_rejects_wrong_date() -> None:
    assert not answer_verify("September 18, 2001", "2001-9-17")
    assert not answer_verify("August, 2023", "2024-08-01")


def test_answer_verify_accepts_or_alternatives() -> None:
    assert answer_verify("The combined total is **30**.", "35 or 30")
    assert answer_verify("Total: 44 operas combined.", "54 or 44")
    assert answer_verify(
        '{"flight_distance": "12,000 miles", "train_distance": "4000 miles"}',
        "16,000 or 12,000, 4,000",
    )
    assert answer_verify(
        "2 opera halves ### 30,000 people deported",
        "30,002 or 2, 30,000",
    )
    assert answer_verify("### Laptops:\n3 brands.\n### Smartphones:\n2 brands.", "5 or 3, 2")
    assert answer_verify(
        "Billy Graham's LA Crusade start (Sept 25, 1949) is more recent than the Greek Civil War's end (Aug 31, 1949).",
        "The start of Billy Graham's Los Angeles Crusade or Billy Graham",
    )
    assert answer_verify(
        '{"answer": 8} Human brain has 4 ventricles; bird heart has 4 chambers; combined total is 8.',
        "6 or 8",
    )
    assert answer_verify('{"comparison": false, "reasoning": "..."}', "no or false")
    assert answer_verify('{"comparison_result": false}.', "no or false")
    assert not answer_verify("The combined total is **30**.", "35")
    assert not answer_verify("Total: 44 operas combined.", "54")
