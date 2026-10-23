# Copiloto conversacional v2 — primeira entrega

Status: primeira entrega da V2 após o corte de dados da identidade. O copiloto é auxiliar; nunca altera regras, auditorias, achados, casos ou decisões. Sem Ollama, retorna uma limitação explícita.

Extensão posterior: `organization-copilot-agent-v1.md` acrescenta o chat de
organização sem alvo específico. As regras abaixo de alvo único continuam
aplicáveis aos chats por achado ou auditoria.

## Escopo e autorização

- Cada chat tem exatamente um alvo: um achado ou uma auditoria concluída da organização ativa. Owner, Admin e Analyst com associação ativa podem perguntar; Viewer consulta apenas os dados determinísticos existentes.
- O modo **normal** salva perguntas e respostas na organização. O autor pode reler ou excluir seu chat. Outros usuários não recebem a transcrição pela API, mas turnos normais aprovados podem alimentar a memória compartilhada da mesma organização. Toda resposta exige citações de evidências da organização verificadas no servidor. Revogação de associação impede novas leituras e perguntas.
- O modo **temporário** usa os turnos anteriores do próprio chat e evidências do alvo. Não consulta outros chats, não entra na memória, não aparece em listagens e não é restaurado pela interface após recarregar. Registros transitórios necessários ao job são apagados após 1 hora de inatividade; jobs não carregam pergunta ou resposta no payload.
- Por padrão, o modo inicial é normal. Owner/Admin podem tornar temporário o padrão da organização. Nesse caso, Owner/Admin podem iniciar chat normal diretamente; Analyst precisa solicitar e aguardar aprovação de Owner/Admin para cada chat normal. Chat pendente não aceita perguntas nem entra na memória. A política pertence ao domínio de negócios, sem leitura direta de tabelas da identidade.
- A política também define o máximo de turnos de outros chats recuperados por resposta (0–20; padrão 10). Todos os chats normais ativos da organização são elegíveis; o limite seleciona os turnos mais recentes, pois todo o histórico não cabe no contexto. Valor 0 desliga memória entre chats. O histórico do chat atual permanece disponível dentro do limite.
- Owner/Admin podem salvar até 2.000 caracteres de instruções da organização para o tom e o foco das respostas do copiloto e da explicação opcional dos alertas. A ausência do campo em um `PUT` antigo preserva as instruções atuais. O texto é isolado por organização, aplicado na próxima geração (sem reescrever respostas já salvas) e nunca registrado em logs. As instruções não podem remover a exigência de evidências/citações, ampliar acesso, alterar a auditoria determinística ou autorizar ações. Texto vazio restaura o comportamento padrão.

## Contrato HTTP

Todos os caminhos têm prefixo `/api/v1/organizations/{organization_id}/ai`. Mutações exigem sessão, CSRF e `Origin` válido; leituras exigem sessão. IDs de alvo e recurso são sempre filtrados por `organization_id`.

| Operação | Resposta e regra |
| --- | --- |
| `GET /copilot/policy` | Modo padrão, limite de memória e instruções da organização; associação ativa necessária. |
| `PUT /copilot/policy` | Owner/Admin ajusta `temporary_default`, `memory_turn_limit` (0–20) e, opcionalmente, `instructions` (até 2.000 caracteres); 200. Campo omitido preserva as instruções. |
| `POST /copilot/conversations` | `{finding_id|audit_id, mode}`; exatamente um alvo concluído. 201 com `active` ou `pending`; temporário expira. |
| `GET /copilot/conversations?finding_id=...|audit_id=...` | Página cursor/limitada de chats normais do autor; exclui temporários e rejeitados. |
| `GET /copilot/conversations/{id}` | Autor lê chat e página de turnos; temporário acessível enquanto não expirado. |
| `GET /copilot/approvals` | Owner/Admin lista chats pendentes, sem transcrição. |
| `POST /copilot/conversations/{id}/approve` ou `/reject` | Owner/Admin decide pedido; decisão igual é idempotente, oposta retorna 409. |
| `POST /copilot/conversations/{id}/questions` | Pergunta de 1–1000 caracteres e `Idempotency-Key` de 8–128; 202 com turno/job. Um turno por chat em andamento; repetição da chave devolve o mesmo turno, conflito de conteúdo retorna 409. |
| `GET /copilot/questions/{id}` | Apenas o autor obtém estado, resposta, limitação e citações verificadas; 404 após expiração. |
| `DELETE /copilot/conversations/{id}` | Autor exclui chat e turnos; pergunta em andamento retorna 409. Chat normal removido deixa a memória. |

Coleções usam limite máximo de 50 e cursor estável. Erros usam o envelope padrão. Resultados não incluem conteúdo de outros chats. A interface não armazena ID temporário em localStorage nem na URL.

## Dados e processamento

- `CopilotPolicy(organization_id, temporary_default, memory_turn_limit, instructions)` pertence a `business`; ausência de linha equivale a normal/10/instruções vazias. `CopilotConversation` guarda organização, autor, alvo, modo, status (`active`, `pending`, `rejected`), decisão, expiração e timestamps. `CopilotTurn` guarda organização, conversa, autor, chave idempotente, pergunta, resposta estruturada, IDs de evidência, hash do contexto, estado, job e expiração. Índices por tenant/autor/alvo/data e FKs compostas entre tabelas de negócios. Migração aditiva.
- O worker existente aceita job `copilot`. O payload contém apenas ID do turno. A aquisição do job e da conversa serializa turnos; falhas e lease expirado marcam o turno como falho. Pergunta e histórico nunca aparecem em logs ou eventos.
- O contexto do alvo usa `build_ai_context` (até 20 achados, 50 evidências, 2 KiB por evidência). Inclui no máximo os 10 turnos anteriores do chat atual. No modo normal, acrescenta até `memory_turn_limit` turnos normais ativos de outros chats da mesma organização, por data decrescente. Para cada memória, o servidor busca novamente as evidências citadas e confirma tenant e alvo; descarta turnos sem evidência válida. O contexto total tem teto de bytes e informa truncamento.
- O modelo recebe instrução de sistema separada de pergunta, histórico e evidências não confiáveis; temperatura zero, lista explícita de IDs de evidência permitidos e schema JSON estrito `{answer,evidence_ids}`. O servidor rejeita IDs inexistentes, de outro tenant ou fora do contexto, inclusive UUIDs escritos no texto. Saída inválida pode receber uma segunda tentativa com instrução corretiva, sem relaxar a validação. A resposta retorna citações com ID de evidência e respectivos achado/auditoria. Sem evidência suficiente, modelo indisponível ou saída ainda inválida, o turno falha com limitação clara. Auditoria determinística continua utilizável.
- Limpeza de temporários expirados remove transcrição/resposta e torna IDs inacessíveis; jobs concluídos podem manter só metadados técnicos sem conteúdo. Chats normais não são apagados sem pedido do autor.

## UI e aceite

Painéis nos detalhes de achado e auditoria apresentam seletor de modo antes de iniciar, histórico do chat, estado de aprovação, envio/processamento/falha, citações navegáveis e aviso de IA auxiliar. Configurações expõem política e fila de aprovação para Owner/Admin. O temporário desaparece ao recarregar. Interface funciona com teclado, foco visível e tela móvel.

Configurações separam parâmetros de auditoria da aba **IA**. A aba IA permite editar/remover instruções da organização, explica que elas valem apenas para novas respostas e mantém modo temporário, memória e aprovações no mesmo local. Apenas Owner/Admin podem salvar; entrada inválida não altera a política. Testes cobrem autorização, isolamento, preservação em PUT legado, limite de tamanho e inclusão no prompt de ambos os fluxos sem enfraquecer a validação de evidências.

Testes cobrem alvo e modo inválidos, autorização/CSRF, dois tenants, usuário revogado, aprovação e rejeição, idempotência, concorrência de turnos, memória permitida/proibida, limites de contexto, injeção em pergunta/histórico/evidência, citações inventadas, Ollama indisponível, limpeza temporária e E2E dos dois modos. OpenAPI e guia do usuário acompanham a implementação.
