import os

from openai import APITimeoutError, OpenAI

client = OpenAI(timeout=60.0, max_retries=0)

INSTRUCTIONS = """
Extraia o valor final a pagar da fatura.
Responda apenas com um objeto JSON com a chave "total_amount".
Use uma string com ponto decimal e duas casas, sem símbolo de moeda.
Se o documento não identificar o valor final a pagar, use null.
""".strip()


def call_llm(text: str) -> str:
    try:
        response = client.responses.create(
            model=os.environ["OPENAI_MODEL"],
            instructions=INSTRUCTIONS,
            input=text,
        )
    except APITimeoutError as exc:
        raise TimeoutError("OpenAI request timed out") from exc

    return response.output_text