# Validação do agente empresarial v1

Data: 29/10/2026. Branch: `codex/enterprise-agent-foundation`.

## Evidências

- CI do PR #54 no commit `d9953f2`: 14/14 checks concluídos com sucesso,
  incluindo API, navegador, build ARM64, recuperação do broker e configuração
  da demonstração.
- Migração `e8a91f76c203`: upgrade, downgrade e novo upgrade passaram em
  PostgreSQL descartável antes da instalação da demo.
- Demo Quick Tunnel isolada: backup quiescido criado e verificado antes do
  upgrade; migração e provisionamento de papéis passaram. O gate
  `verify_deployment.py` retornou `status: ok` após subir os 11 serviços.
- Ollama local `gemma3:4b`: o worker acessou o catálogo do modelo pelo
  `host.docker.internal`; uma pergunta sobre procedimento sintético gerou
  resposta estruturada e citação válida.
- E2E público com `PROCESSMIND_REQUIRE_MODEL=1`: o cenário do agente flutuante
  passou, incluindo criação de empresa e fonte, ativação, resposta real,
  citação documental e abertura do documento. O fluxo completo de importação,
  auditoria, análise de compras com citações, caso e revisão também passou.
- Typecheck e ESLint do frontend passaram; o lint reportou cinco avisos já
  existentes de Fast Refresh, sem erros.

## Limites observados

- Uma pergunta genérica sobre quais achados revisar produziu resposta do
  modelo sem citação válida. O backend a recusou e exibiu limitação explícita.
  O cenário de compras usa pedido inequívoco de análise. A qualidade de
  respostas para perguntas vagas deve ser medida antes de ampliar a seleção
  de ferramentas.
- O endereço do Quick Tunnel é temporário. Este registro não o trata como
  implantação permanente nem como ambiente de produção.
