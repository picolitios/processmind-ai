# Avaliação do motor determinístico v1.0.0

Executada em 2026-10-14 com semente 42 e `scripts/evaluate_audit.py`. O script gera CSV e gabarito, normaliza as linhas com o mesmo parser da API e chama o motor versionado. O teste de integração PostgreSQL cobre persistência de job, achados e evidências separadamente. TP/FP/FN são comparados por número físico de linha; para DUPLICATE, o par de compras corresponde à linha posterior no CSV. Nenhum limiar foi ajustado depois de observar os resultados.

| Linhas | Válidas | Inválidas | DUPLICATE TP/FP/FN | INVALID_QUANTITY TP/FP/FN | PRICE_OUTLIER TP/FP/FN | LATE_DELIVERY TP/FP/FN | INCOMPLETE_RECORD TP/FP/FN | Preço inconclusivo |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 99 | 1 | 1/0/0 | 1/0/0 | 1/0/1 | 2/0/0 | 1/0/0 | 47 |
| 1.000 | 990 | 10 | 18/0/0 | 5/0/0 | 21/0/0 | 24/0/0 | 10/0/0 | 2 |
| 10.000 | 9.897 | 103 | 187/0/0 | 52/0/0 | 206/0/0 | 232/0/0 | 103/0/0 | 0 |
| 50.000 | 49.485 | 515 | 934/0/0 | 258/0/0 | 1.033/0/0 | 1.159/0/0 | 515/0/0 | 0 |

Nas cinco regras com positivos sintéticos, precisão e recall são 1,0 a partir de 1.000 linhas. Em 100 linhas, PRICE_OUTLIER tem precisão 1,0 e recall 0,5; a outra ocorrência não possui cinco pares comparáveis e permanece inconclusiva. TOTAL_MISMATCH, INVALID_DATES, RECURRING_DELAY e OVER_LIMIT não têm positivos nesse gerador: TP/FP/FN são 0/0/0, e precisão/recall são indefinidos. Essas regras são cobertas por casos dirigidos em `apps/api/tests/test_audit_rules.py`.

Reprodução no PowerShell, com dependências da API instaladas:

```powershell
.\apps\api\.venv\Scripts\python scripts/evaluate_audit.py --sizes 100 1000 10000 50000 --seed 42 --assert-gates --output-dir synthetic-output
```

O gate automatizado exige FP=FN=0 em DUPLICATE, INVALID_QUANTITY, LATE_DELIVERY e INCOMPLETE_RECORD para conjuntos de pelo menos 1.000 linhas. Ele não afirma desempenho em dados reais nem classifica fraude. Testes de carga e limiares operacionais de tempo/memória pertencem à Fase 7.
