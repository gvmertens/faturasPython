from decimal import Decimal
from extraction import classify_amount_error, extract_total_amount


def is_amount_correct(extracted: Decimal | None, expected: Decimal) -> bool:
    return extracted is not None and extracted == expected


def count_correct_amounts(cases: list[tuple[Decimal | None, Decimal]]) -> int:
    count = 0
    for extracted, expected in cases:
        if is_amount_correct(extracted, expected):
            count += 1
    return count


def calculate_accuracy(correct_count: int, total_count: int) -> float | None:
    if total_count == 0:
        return None
    return correct_count / total_count * 100


def evaluate_amount_extraction(cases: list[dict]) -> float | None:
    correct_count = 0
    for case in cases:
        total = extract_total_amount(case["text"])
        if is_amount_correct(total, case["expected_amount"]):
            correct_count += 1
    return calculate_accuracy(correct_count, len(cases))


def select_evaluation_cases(cases: list[dict]) -> list[dict]:
    selected = []
    for case in cases:
        if case["split"] == "evaluation":
            selected.append(case)
    return selected


def evaluate_reserved_cases(cases: list[dict]) -> float | None:
    evaluation_cases = select_evaluation_cases(cases)
    return evaluate_amount_extraction(evaluation_cases)


def build_evaluation_report(cases: list[dict]) -> dict:
    evaluation_cases = select_evaluation_cases(cases)
    correct_count = 0
    failures = []

    for case in evaluation_cases:
        extracted = extract_total_amount(case["text"])

        if is_amount_correct(extracted, case["expected_amount"]):
            correct_count += 1
        else:
            failures.append(
                {
                    "id": case["id"],
                    "reason": classify_amount_error(extracted, case["expected_amount"]),
                    "expected_amount": case["expected_amount"],
                    "extracted_amount": extracted,
                }
            )

    return {
        "evaluated_count": len(evaluation_cases),
        "correct_count": correct_count,
        "accuracy": calculate_accuracy(correct_count, len(evaluation_cases)),
        "failures": failures,
        "failure_counts": count_failures_by_reason(failures),
    }


def count_failures_by_reason(failures: list[dict]) -> dict:
    counts = {}

    for failure in failures:
        reason = failure["reason"]
        counts[reason] = counts.get(reason, 0) + 1

    return counts
