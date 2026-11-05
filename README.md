# Curso de engenharia de IA — checkpoint 04/11/2026

Requer Python 3.10+. Sem dependências externas. Na pasta deste README:

```bash
python -m unittest -v
```

- extraction.py: modelo Invoice, validações e extração de dois campos de texto.
- evaluation.py: comparação com gabarito e percentual de acerto do total.
- test_course.py: suíte consolidada usando unittest, da biblioteca padrão.

Nos testes, self.assertEqual(a, b) corresponde a assert a == b;
self.assertIsNone(value) verifica value is None. subTest identifica cada exemplo.
O extrator retorna um dicionário de dois campos, ainda não uma Invoice completa.

## Limitações preservadas

Fornecedor exige prefixo exato Fornecedor: e pode retornar string vazia.
Apenas TOTAL A PAGAR e VALOR DA FATURA são rótulos de total reconhecidos.
A primeira linha reconhecida encerra a busca, inclusive quando o valor é inválido.
Conflitos entre múltiplos totais não são detectados.
Valores exigem vírgula e duas casas decimais; R$ opcional, sem sinais.
Ausência e formato inválido retornam None, sem motivo separado.
needs_review verifica apenas None e não garante correção.
Avaliação pressupõe contagens válidas e gabaritos Decimal.
Os exemplos sintéticos foram usados no desenvolvimento: não são teste independente.
Sem PDF, OCR ou LLM. Nenhuma regra nova foi adicionada neste checkpoint.

## Próximo exercício

Criar teste de evaluate_amount_extraction com um documento contendo
Total devido: R$ 89,90 e gabarito Decimal('89.90'). Medir antes de mudar o extrator.

Referência complementar:
https://github.com/unipds-engenharia-de-ia-aplicada/engenharia-de-software-com-ia-aplicada
