# Validação do modelo local do copiloto na demo

Execução em 20/10/2026, no Windows com Docker Desktop, Ollama 0.40.6 e
`gemma3:4b`. O modelo foi obtido localmente pelo catálogo do Ollama; nenhuma
API de inferência paga ou infraestrutura Oracle foi usada.

- Ollama respondeu em `127.0.0.1:11434`; `model-worker` alcançou `/api/tags`
  pelo `host.docker.internal` e encontrou `gemma3:4b`.
- Chamada sintética direta pelo contrato `CopilotResult` retornou uma resposta
  com uma evidência validada pelo servidor. A primeira inferência levou 117,9 s,
  próxima do timeout de 120 s. O desempenho depende da máquina e do contexto.
- `python scripts/quickdemo.py enable-model` recriou apenas o `model-worker`,
  preservando a URL pública e os demais containers.
- Readiness na URL pública temporária retornou HTTP 200. Com
  `PROCESSMIND_REQUIRE_MODEL=1`, `npm run test:e2e` passou: 3 testes em 1,5 min.
  O fluxo principal criou organização, importou CSV sintético, executou auditoria,
  recebeu respostas reais com citações nos chats normal e temporário, resolveu
  caso e salvou política do copiloto.

O teste usa dados sintéticos e não registra prompts, respostas, credenciais ou
URLs temporárias neste documento. A URL Quick Tunnel muda ao reiniciar; o modelo
requer que Ollama permaneça ativo no computador do operador.
