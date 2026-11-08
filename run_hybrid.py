from unittest.mock import Mock

from extraction import extract_total_with_fallback
from run_baseline import cases
from collections.abc import Callable
from time import perf_counter

def simulate_llm(text: str) -> str:
    if text == next(case["text"] for case in cases if case["id"] == "B-05"):
        raise TimeoutError("LLM call timed out")

    return responses[text]

def evaluate_hybrid_batch(cases: list[dict], call_llm: Callable[[str], str]) -> dict:
    correct_count = 0
    reviews = []

    for case in cases:
        try:
            extracted = extract_total_with_fallback(case["text"], call_llm)
        except ValueError:
            reviews.append({"id": case["id"], "reason": "invalid_llm_response"})
            continue
        except TimeoutError:
            reviews.append({"id": case["id"], "reason": "llm_timeout"})
            continue

        if extracted == case["expected_amount"]:
            correct_count += 1

    return {"correct_count": correct_count, "reviews": reviews}


responses = {
    case["text"]: response
    for case in cases
    if (
        response := {
            "B-03": '{"total_amount":"187.35"}',
            "B-05": '{"total_amount": 125.00}',
        }.get(case["id"])
    )
    is not None
}

if __name__ == "__main__":
    from openai_client import call_llm

    llm = Mock(wraps=call_llm)
    ordered_cases = sorted(cases, key=lambda case: case["id"] != "B-05")

    started_at = perf_counter()
    report = evaluate_hybrid_batch(cases, llm)
    elapsed = perf_counter() - started_at

    for review in report["reviews"]:
        print(f'{review["id"]}: encaminhar para revisão ({review["reason"]})')

    print(f'Acertos: {report["correct_count"]}/{len(ordered_cases)}')
    print(f"Chamadas ao modelo: {llm.call_count}")
    print(f"Tempo do lote: {elapsed:.2f} s")
