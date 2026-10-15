# Fase 7 — plano de estabilização

## Objetivo e fronteiras

Validar o MVP entregue nas Fases 1–6 antes da instalação limpa da Fase 8. Corrigir apenas falhas de segurança, carga, acessibilidade e regressões encontradas. Não acrescentar regras de auditoria ou recursos pós-MVP.

## Ordem de execução

1. Revisar headers do web e cache de respostas empresariais; medir dependências de runtime e verificar que E2E e API seguem funcionais sob CSP.
2. Exercitar teclado, foco, nomes acessíveis, estados de erro e visualização móvel nas onze telas. Registrar achados e correções; automatizar os invariantes repetíveis com Playwright.
3. Reproduzir corpus sintético de 100, 1.000, 10.000 e 50.000 compras, medindo tempo de ingestão/auditoria, pico de memória, paginação e execução concorrente por organização. Registrar ambiente, semente e números medidos em `phase7-load-report.md` antes de definir limites operacionais finais.
4. Reexecutar isolamento entre tenants, CSRF, RBAC, uploads adversariais, dependências, migrações, lint, tipos, testes e E2E. Registrar riscos residuais e resultados em relatório da Fase 7.

## Critérios verificáveis

- Headers de segurança presentes no web, sem bloquear os fluxos do produto. API com `Cache-Control: no-store` em dados empresariais e de autenticação. Nenhuma credencial em Git ou log de teste.
- Fluxos essenciais utilizáveis apenas com teclado, com foco visível, nomes claros e erro associado ao formulário; layout utilizável em 390 px sem ocultar ações essenciais.
- Os quatro tamanhos de corpus completam sem falha, e o relatório expõe tempo, memória e gargalos. Coleções continuam paginadas e a concorrência não causa vazamento entre organizações nem duplicação de jobs.
- Gates locais e CI passam; desvios são corrigidos ou documentados como riscos reais antes de declarar a Fase 7 concluída.
