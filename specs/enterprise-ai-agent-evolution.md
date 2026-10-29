# Evolução do ProcessMind AI para agente empresarial

Status: auditoria da Fase 0 e contrato incremental da primeira versão (29/10/2026).
Fonte: proposta anexada pelo usuário e fluxo priorizado nesta tarefa. Esta spec não
declara conectores externos, documentos empresariais ou agente flutuante como
funcionalidades já existentes.

## Estado verificado

| Área | Situação atual | Lacuna para o fluxo pedido |
| --- | --- | --- |
| Identidade | Cadastro, sessão HttpOnly/CSRF/Origin, organização ativa, membros e papéis owner/admin/analyst/viewer | Criação já ativa; não existe classificação nem aprovação administrativa separada. |
| Compras | CSV/XLSX, compras normalizadas, auditoria determinística, achados, evidências, casos | O copiloto lê achados/evidências, mas não há catálogo de ferramentas habilitadas por organização. |
| IA | Ollama local opcional, worker separado, chats normais/temporários, memória e citações de evidências verificadas | Chat só existe em páginas dedicadas; exige evidência de auditoria e não pesquisa documentação empresarial. |
| Interface | SPA React, navegação por organização, tema claro/escuro, painel de chat em página própria | Falta painel flutuante compartilhado e administração de fontes/ferramentas. |
| Infraestrutura | Compose, PostgreSQL, Alembic, CI/E2E, demo Quick Tunnel sintética | Nenhum serviço de conectores, gestão de segredos de integrações ou hospedagem permanente. |

Arquitetura atual: Nginx serve React e encaminha API; identidade e API empresarial
são processos FastAPI distintos, com autorização de vínculo em cada operação.
Dados empresariais usam schema `business` e `organization_id`; workers usam
jobs persistidos. O banco e Ollama são locais na demonstração. Os recursos acima
foram identificados no código e nas specs existentes; não há classificação
empresarial implementada para reutilizar.

## Resultado da primeira versão

1. O owner cria a organização pelo fluxo atual. Ela se torna ativa após o
   provisionamento da configuração de auditoria já existente. A tela exibe o
   estado; não se inventa uma etapa de aprovação ou classificação.
2. Owner/Admin adiciona uma fonte de **documentação gerenciada** à organização,
   informando título e conteúdo textual de um procedimento autorizado, e a
   habilita. Esse é o primeiro conector: dados controlados pela própria empresa,
   sem credencial externa nem falsa indicação de conexão a ERP. A fonte pode ser
   desabilitada; sua revisão e autor ficam registrados. Integrações REST/OAuth
   ficam para a Fase 4 após definição de provedor/credenciais/escopos.
3. Owner/Admin habilita separadamente o agente e a ferramenta de auditoria de
   compras. Por padrão em organizações legadas, a ferramenta de compras mantém
   o comportamento atual; o novo agente fica desabilitado até configuração.
4. Membro autorizado vê um botão flutuante em telas da organização e abre um
   painel sem perder a página. A conversa reutiliza política, persistência e
   worker existentes. A disponibilidade do botão depende do backend.
5. Perguntas sobre processo buscam primeiro documentação habilitada do tenant.
   Busca textual limitada; sem fonte correspondente, o agente informa ausência
   de evidência. Resposta distingue informação documental e inferência.
6. Citações de documento são IDs e trechos resolvidos pelo servidor, com link
   para a fonte autorizada. Conteúdo da fonte é dado não confiável, nunca
   instrução de sistema. Desabilitação/revogação invalida citações e futuras
   recuperações. Perguntas de compras usam a ferramenta determinística existente
   somente se habilitada, e citam evidências de auditorias concluídas.
7. A IA não cria auditoria, altera compra, caso ou configuração. Se Ollama
   estiver indisponível, a limitação é explícita; consultas e auditorias
   determinísticas permanecem funcionais.

## Decisões arquiteturais

- Preservar os endpoints e dados do copiloto existente. Adicionar uma camada de
  seleção de fontes/ferramentas no backend, sem permitir que o prompt autorize
  acesso. Usar o serviço de identidade para validar empresa ativa e papel em
  toda requisição. Contexto de rota é apenas dica, nunca autorização.
- O registro de conectores é tipado e fechado nesta versão:
  `managed_knowledge` é local e não usa credenciais. Nenhum endpoint aceita
  URL arbitrária, SQL, token ou código executável; isso evita SSRF, vazamento e
  uma promessa falsa de integração genérica. Adaptadores futuros seguem
  interface de capacidades, saúde e escopo; seus segredos precisarão de cofre
  ou criptografia com chave fora do banco.
- Uma fonte pode conter texto puro limitado e título; não aceitar HTML,
  scripts, fórmulas ou arquivos nesta primeira versão. Buscar trechos com
  PostgreSQL, filtrar tenant e estado ativo antes do modelo, limitar número
  e bytes; citar apenas IDs efetivamente enviados. Sanitizar saída na UI.
- Reutilizar as regras de memória normal/temporária e idempotência. Citações
  passam a ter tipo `audit_evidence` ou `knowledge_source`; o backend resolve
  cada tipo e valida tenant/estado a cada leitura. Memórias com fonte revogada
  não são reutilizadas. Nunca registrar prompts, documentos ou segredos em logs.
- A configuração de ferramenta pertence ao domínio empresarial, separado da
  identidade. Migração Alembic aditiva cria tabelas com índice por organização
  e `CHECK` para limites de conteúdo; não cria FK ao schema de identidade.
  Downgrade recusa perda
  silenciosa de fontes ou configurações em uso. Dados legados preservados.

## Contratos planejados

Prefixo: `/api/v1/organizations/{organization_id}`. Sessão em todas as
operações; CSRF e Origin em mutações; 404 para recurso de outro tenant.

| Método e caminho | Papel | Comportamento |
| --- | --- | --- |
| GET/PUT `/agent/configuration` | membro / owner-admin | Catálogo e flags de agente e compras; PUT aceita booleans explícitos e gera evento sem conteúdo. |
| GET/POST `/integrations/knowledge` | membro / owner-admin | Listagem paginada e criação limitada de fonte textual. |
| GET/PATCH `/integrations/knowledge/{id}` | membro / owner-admin | Detalhe e edição de título/conteúdo/estado; revogação impede novas respostas. |
| GET `/agent/capabilities` | membro | Capacidades efetivas para o papel e a organização, estado das fontes. |
| POST `/ai/copilot/conversations` | owner/admin/analyst | Reutiliza `scope=organization` e modos normal/temporário existentes; exige agente habilitado para o painel flutuante. |
| POST `/ai/copilot/conversations/{id}/questions` | autor autorizado | Seleção de documentação ou auditoria; job existente e idempotência. |
| GET `/ai/copilot/questions/{id}` | autor autorizado | Resposta, limitação, ferramentas usadas e citações tipadas verificadas. |

Erros: envelope padrão, 401 sessão, 403 papel/capacidade, 404 recurso ausente
ou de outro tenant, 409 estado conflitante, 422 entrada inválida, 503 fonte
indisponível. Coleções têm limite/cursor; mutações são auditadas sem texto.

## Sequência, testes e aceite

Fase 0: este documento e revisão das divergências. Fase 1: catálogo mínimo,
ativação, painel flutuante e perguntas sobre documentação. Fase 2: integrar
compras existentes como ferramenta selecionável. Fase 3: gestão e revogação de
fontes por organização. Fase 4: conector REST real somente após fonte autorizada
e modelo seguro de credenciais. Fase 5: otimizações baseadas em medição.

Gates da primeira versão: migração upgrade/downgrade em banco descartável;
Ruff, Mypy, Pytest, lint, tipos, build, Vitest, E2E Compose. Cobrir tenant
cruzado, viewer, associação revogada, CSRF, fonte desabilitada, ferramenta
desabilitada, documento malicioso, citação inventada, limites, falha do modelo,
foco/teclado/mobile, fluxo completo e regressão de importação/auditoria/casos.
Deploy só é declarado após verificação na URL correspondente. Demo usa apenas
dados sintéticos e custo zero; Ollama local e Quick Tunnel dependem do PC ligado.

Riscos: documento empresarial pode conter dados sensíveis; demonstrar apenas
com texto sintético. PostgreSQL e volume local exigem backup. Quick Tunnel tem
URL efêmera. O modelo pode falhar ou recusar saída estruturada; isso não pode
ser descrito como resposta bem sucedida. Conectores externos exigirão
autorização explícita, escopos e gestão de segredos antes de qualquer acesso.
