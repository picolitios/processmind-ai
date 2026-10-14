# Motor determinístico v1.0.0 (Fase 4)

Escopo da execução: apenas `ImportBatch` concluídos selecionados na mesma organização. O snapshot de configuração e de versão é persistido em `AuditRun`; compras e erros de importação são lidos na transação do worker. Cada achado recebe fingerprint estável por execução, regra e IDs de origem. Nenhuma regra afirma fraude: os achados pedem revisão humana.

| Regra | Condição v1 | Severidade |
| --- | --- | --- |
| DUPLICATE | Mesmos fornecedor, produto, data, quantidade, preço unitário, total e moeda em compras distintas; o par é o alvo e ambas as compras são evidência. ID externo repetido na mesma importação já é erro de validação. | high |
| TOTAL_MISMATCH | Diferença absoluta entre total declarado e quantidade × preço unitário maior que 0,01. | medium |
| INVALID_QUANTITY | Linha de origem com quantidade numérica não positiva; nunca cria `Purchase`. | medium |
| PRICE_OUTLIER | Mesmo produto, moeda e unidade não vazia, dentro de ±90 dias. Exige 5 pares válidos além da compra avaliada. Fora de `mediana ± max(3×IQR, 4,4478×MAD, 25%×mediana)`. Sem amostra, o resultado é inconclusivo e não cria achado. | medium |
| INVALID_DATES | Entrega prevista ou real anterior à compra; entrega real preenchida sem data prevista. | medium |
| LATE_DELIVERY | Entrega real posterior à prevista; evidência inclui dias de atraso. | low |
| RECURRING_DELAY | Fornecedor com ao menos 3 entregas concluídas no período de 90 dias anteriores à última compra selecionada e proporção de atraso ≥50%. Um achado por fornecedor, com numerador, denominador e período. | medium |
| INCOMPLETE_RECORD | Qualquer linha inválida que não gerou `Purchase`, incluindo falta de campo obrigatório ou valor não analisável. | low |
| OVER_LIMIT | Total declarado supera `amount_limits[currency]` no snapshot da organização; sem limite da moeda, inconclusivo. | high |

IQR é Q3−Q1, com quartis por mediana das metades; MAD é a mediana do desvio absoluto à mediana. Limites são estritos: valores exatamente no limite não são achados. Valores Decimal permanecem strings nas evidências JSON. O período de `RECURRING_DELAY` usa `delay_window_days` da organização quando configurado, caso contrário 90. O limite de preço por organização não existe nesta versão; `amount_limits` pertence a `OVER_LIMIT`.

## Avaliação do corpus

O gerador de semente fixa registra números físicos das linhas CSV, incluindo cabeçalho. `DUPLICATE`, `LATE_DELIVERY`, `INVALID_QUANTITY` e `INCOMPLETE_RECORD` devem detectar 100% dos casos inequívocos do gabarito em 1 mil linhas. Para `PRICE_OUTLIER`, registrar TP/FP/FN, precisão, recall e inconclusivos por tamanho, sem ajustar o limiar depois da avaliação. O gabarito de 100 linhas pode ter amostra insuficiente. As demais regras recebem testes dirigidos com casos de borda. Resultados da avaliação ficam em `specs/testing/audit-evaluation.md`.
