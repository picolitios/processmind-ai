# Fase 7 — resultado da estabilização

## Escopo e correções

- Web: CSP e headers de proteção; API: `Cache-Control: no-store` em `/api/v1/`. O E2E confirma os headers e ausência de erros de CSP no fluxo.
- Acessibilidade: corrigido contraste de texto secundário, botão principal e estados. Axe com regras WCAG 2.0/2.1 A e AA passa no fluxo que visita as onze telas. O teste móvel em 390 px verifica foco visível, ordem inicial de teclado, navegação por Enter e ausência de rolagem horizontal nas telas de acesso e importações.
- Ingestão: processamento em lotes de 500 linhas, UUID definido antes da gravação e cache de fornecedores por job. O teste concorrente verifica dois tenants, uma compra por importação e negação de acesso cruzado. Tempos e memória estão em `phase7-load-report.md`.
- Dependências: `@axe-core/playwright` automatiza acessibilidade nos E2E; `psutil` mede RSS no benchmark. `pip` foi atualizado na imagem da API e a faixa de `pytest` de desenvolvimento foi ajustada após auditoria.

## Gates executados em 15/10/2026

| Gate | Resultado |
| --- | --- |
| Migração Alembic em PostgreSQL novo e testes da API | 18 passaram; aviso de depreciação do `TestClient` de Starlette/httpx |
| Ruff, mypy, validador de specs e avaliação do gabarito sintético de 1.000 linhas | Passaram |
| Web lint, typecheck, Vitest e build de produção | Passaram; lint mantém cinco avisos de Fast Refresh sem erros |
| Playwright: fluxo completo, acessibilidade móvel e headers | 3 passaram |
| Auditoria npm de dependências de produção e pip-audit do ambiente Python | Nenhuma vulnerabilidade conhecida encontrada |
| Benchmark 100/1.000/10.000/50.000 linhas | Concluído, sem falhas; paginação e contagens verificadas |

## Limites conhecidos

- O benchmark mede o processo Python no host de desenvolvimento. Não estabelece SLO de produção nem mede o pico de memória total do Compose; repetir em infraestrutura representativa antes de definir capacidade contratual.
- O teste de concorrência cobre duas importações pequenas. Carga concorrente de 50.000 linhas não foi medida.
- A checagem automatizada de acessibilidade não substitui avaliação manual com leitores de tela. O teste de teclado cobre acesso e navegação essencial em tela móvel.
- O aviso de depreciação do `TestClient` não afeta os testes atuais; acompanhar a atualização compatível de Starlette/httpx sem trocar dependências fora da faixa estabelecida nesta fase.
