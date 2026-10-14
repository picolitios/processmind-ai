# Estratégia de testes

Testes verificam comportamento e invariantes, com dados sintéticos de semente fixa. CI usa PostgreSQL real em serviço local/contêiner; mocks ficam apenas nas fronteiras externas como Ollama e relógio. Não comparar texto generativo exato.

| Nível | Cobertura prioritária | Gate |
| --- | --- | --- |
| Unitário Python | Decimal, parsing, regras e bordas, estatística, transições, RBAC | Fases 2–6 |
| Integração API/DB | migrações, validação, filtros, paginação, idempotência, jobs, isolamento | Fases 1–7 |
| Web | formulários, acessibilidade básica, estados vazio/erro/carregamento, API client | Fases 2–6 |
| E2E Playwright | cadastro → organização → importação → auditoria → achado → caso → resolução | Fases 6–7 |
| IA | schema, citações válidas, indisponibilidade, prompt injection, dados insuficientes | Fase 5 |
| Carga | 100, 1k, 10k e 50k compras; tempo, memória, paginação e concorrência | Fase 7 |

## Gabarito sintético

Gerador produz CSV/XLSX e JSON de verdade-terreno com IDs e tipo de defeito. A avaliação reporta TP/FP/FN, precisão e recall por regra, sem mascarar falsos positivos de casos ambíguos. Limiares de aceitação numéricos devem ser fixados com corpus versionado na Fase 4, antes de ajustar as regras; para regras exatas (total, quantidade, datas), expectativa é detectar 100% dos casos sintéticos inequívocos. Para preço, registrar inconclusivos e amostra, sem prometer classificação perfeita.

## Gates por fase

Fase 0: links, IDs, cobertura de requisitos e coerência de contratos revisados. Fase 1: compose sobe, migrations aplicam, readiness conecta ao banco, Ruff/Mypy/Pytest e lint/typecheck/build/Vitest passam. Fase 2: dois tenants e papéis, sessão e CSRF. Fase 3: CSV/XLSX válidos e adversariais. Fase 4: gabarito e idempotência. Fase 5: fallback e evidências. Fase 6: fluxo E2E. Fase 7: segurança, carga e acessibilidade. Fase 8: instalação limpa documentada.

Cada correção reexecuta a validação pertinente. Falha de ferramenta indisponível deve ser registrada, sem ser relatada como aprovação.
