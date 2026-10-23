# Explicações assistidas por IA v1

Escopo da Fase 5: uma análise opcional de um achado ou de uma auditoria já concluída. O resultado não altera regras, achados, severidades ou decisões de revisão.

## Fluxo e limites

- `POST /ai/analyses` exige sessão, CSRF, papel owner/admin/analyst, chave de idempotência e exatamente um `finding_id` ou `audit_id` do tenant. A auditoria precisa estar concluída. Repetição da chave com outro alvo retorna 409. O `JobRef` inclui `analysis_id` para a consulta subsequente.
- O job `ai` lê até 20 achados e 50 evidências, em ordem estável. Um achado sem evidência ou auditoria sem achados termina com `failed` e limitação clara, sem chamar Ollama. Se o contexto ultrapassar os limites, a limitação informa que a análise é parcial.
- Apenas código, severidade, explicação determinística e dados de evidências selecionadas chegam ao modelo. Dados externos são serializados como JSON delimitado e tratados como dados, nunca instruções. Cada objeto de evidência é limitado a 2 KiB; conteúdo maior é substituído por marcador de truncamento.
- Para `DUPLICATE`, cada evidência selecionada inclui os campos comparados da compra correspondente, resolvidos por `organization_id` no momento da análise. A explicação deve distinguir o fato observado (campos iguais) da hipótese de erro e orientar a conferência dos documentos de origem.
- O worker chama Ollama local via `/api/chat`, `stream=false`, `format` igual ao JSON Schema e temperatura zero. URL, modelo e timeout são configuração do servidor. A resposta é validada novamente pelo servidor; campos extras, valores fora dos limites, IDs desconhecidos ou ausência de citação são recusados. Texto gerado permanece sugestão, não conclusão automática.
- O contexto explicita os IDs de evidência permitidos. Se a saída não passar na validação de schema ou citações, o worker tenta uma segunda geração com instrução corretiva; a validação continua obrigatória. Em `LATE_DELIVERY`, a interface mostra os dias e as datas calculados pela regra determinística, independentemente da resposta opcional do modelo. Uma análise que ainda falhar pode ser solicitada novamente pelo usuário.
- Indisponibilidade, timeout, saída inválida e contexto insuficiente produzem `status=failed`, resposta vazia e `limitation` explícita. A auditoria determinística continua `succeeded`. O worker não registra prompt, evidência ou resposta em logs. Após três falhas de transporte, o processo abre circuito por cinco minutos.
- `evidence_hash` é SHA-256 do contexto canônico selecionado. A versão do schema e o nome do modelo são persistidos para rastreabilidade. A resposta expõe somente conteúdo validado.

## Aceite

1. Uma resposta válida cita somente IDs presentes no contexto e fica consultável apenas pelo tenant.
2. Injeções no conteúdo da evidência não mudam instruções nem permitem referência inventada.
3. Falha ou ausência do Ollama gera limitação explícita sem apagar achados ou falhar a auditoria.
4. Repetições idempotentes não criam novos jobs; leitores não podem enfileirar análises.
