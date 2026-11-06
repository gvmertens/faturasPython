from decimal import Decimal
from extraction import extract_total_amount

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
        total = extract_total_amount(case['text'])
        if is_amount_correct(total, case['expected_amount']):
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