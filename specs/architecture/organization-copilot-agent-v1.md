# Agente consultivo da organização v1

## Objetivo e limite

O agente usa o Ollama local já integrado para responder, em português, sobre
auditorias concluídas, achados e suas evidências da **organização ativa**. Ele
orienta o usuário e cita evidências verificadas; não cria auditorias, altera
casos, aprova decisões, muda configurações nem executa ferramentas. Esta entrega
não inclui compras brutas, importações, casos ou dados de outras organizações no
contexto do modelo. O fallback explícito continua quando Ollama está ausente.

## Contrato e autorização

- O chat passa a aceitar `{"scope":"organization","mode":"normal|temporary"}`
  em `POST /organizations/{organization_id}/ai/copilot/conversations`. Os
  contratos existentes de `finding_id` e `audit_id` permanecem válidos. Scope e
  IDs de alvo são mutuamente exclusivos. A resposta inclui `scope`, inferido do
  alvo persistido. Uma conversa de organização tem ambos IDs de alvo nulos.
- `GET /conversations?scope=organization` lista apenas os chats normais do
  autor nesse tenant. As listagens por achado/auditoria mantêm a semântica atual.
  Os demais caminhos de detalhe, pergunta, aprovação e exclusão são reutilizados.
- Owner/Admin/Analyst com associação ativa podem usar o agente; Viewer não pode
  perguntar. Uma associação revogada perde acesso. Sessão, CSRF, Origin,
  idempotência, uma pergunta em andamento por chat e paginação seguem a V2.
- O modo normal mantém histórico e memória compartilhada limitada pela política
  da organização. O modo temporário usa apenas o histórico do próprio chat e
  expira; a política de aprovação de chats normais continua valendo.

## Seleção de contexto e segurança

- Em cada pergunta, o servidor seleciona até 20 achados de auditorias
  concluídas da organização. Prioriza correspondências textuais na regra e
  explicação do achado; completa com os achados recentes para perguntas gerais.
  Busca até 50 evidências desses achados em lote, com 2 KiB por evidência e
  limite total do contexto existente. A seleção é limitada, não uma promessa
  de pesquisa exaustiva; a resposta sinaliza contexto parcial quando houver
  mais dados do que o limite.
- Toda consulta filtra `organization_id`; índices e FKs compostas atuais
  continuam isolando os dados. Citações de qualquer chat são resolvidas no
  servidor e exigem evidência da organização e auditoria concluída. O modelo
  nunca recebe credenciais, conteúdo de arquivo importado ou transcrições de
  outros tenants. Pergunta, histórico e evidências continuam não confiáveis.
- Sem evidência selecionada, a pergunta falha com limitação explícita. IDs
  inventados e links produzidos pelo modelo são rejeitados pelo contrato atual.

## Dados, interface e aceite

- A migração aditiva relaxa somente a restrição de alvo para permitir ambos IDs
  nulos; nunca permite ambos preenchidos. O downgrade recusa apagar chats de
  organização. Nenhum dado existente é reescrito.
- Uma rota própria no workspace abre o painel de chat reutilizado com o alvo
  `organization`, modos normal/temporário, aprovações, processamento, erros,
  citações navegáveis e aviso de caráter consultivo. O menu mostra a rota apenas
  para Owner/Admin/Analyst.
- Testes cobrem contrato novo e legado, tenant e papel, seleção limitada,
  evidência de auditoria concluída, memória normal/temporária, citações e
  migração. E2E público exige resposta com citação no chat da organização,
  além dos chats por alvo existentes. O modelo local permanece opcional no CI.
