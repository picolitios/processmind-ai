# Fase 8 — entrega do MVP

## Escopo

Consolidar a documentação para instalação e avaliação técnica do MVP, disponibilizar um CSV de exemplo, capturas de tela e um roteiro de demonstração. Preservar o contrato OpenAPI e registrar backlog pós-MVP. Não adicionar funcionalidades de produto.

## Plano

1. Testar instalação em projeto Compose e volumes novos, sem apagar os dados locais existentes; aplicar todas as migrações e verificar saúde dos serviços.
2. Executar o fluxo funcional E2E nesse ambiente. Gerar capturas das telas de caso e painel usando dados sintéticos.
3. Escrever guia de instalação, uso e demonstração com comandos executáveis; fornecer CSV mínimo e apontar o gerador sintético de quatro tamanhos.
4. Conferir links, OpenAPI, backlog futuro, gates de código pertinentes e coerência com o README. Registrar limitações e resultado da instalação.

## Aceite

Uma pessoa técnica consegue iniciar o Compose, aplicar a migração, cadastrar-se, importar o exemplo, auditar, abrir e encerrar um caso e interpretar o painel seguindo a documentação, sem configuração de IA obrigatória.

## Resultado em 15/10/2026

- O projeto Compose `processmind_phase8` foi criado com volumes PostgreSQL e uploads novos, senha e chave locais geradas para o ensaio em arquivo ignorado pelo Git. `db` e `api` subiram, `alembic upgrade head` aplicou, depois `worker` e `web` subiram. Banco, API e web ficaram saudáveis; `/api/v1/health/ready` e a interface responderam HTTP 200.
- O Playwright executou cadastro → organização → importação do arquivo `examples/compras-exemplo.csv` → auditoria → achado `DUPLICATE` → caso → atribuição → comentário → resolução → indicador. Passou no banco novo. As capturas em `docs/screenshots/` vieram desse fluxo com dados sintéticos.
- Os três E2E passaram no ambiente isolado; lint web passou sem erros (cinco avisos de Fast Refresh já registrados), typecheck, Vitest e build passaram. O validador de specs confirmou 26 caminhos e 60 referências OpenAPI; os 26 caminhos do contrato coincidem com os de runtime após considerar o prefixo `/api/v1`.
- Um verificador de caminhos relativos percorreu 26 documentos Markdown e não encontrou links locais ausentes. O README, os guias, o CSV, as capturas, o backlog futuro e o resumo técnico ficaram vinculados.
- O Compose isolado foi parado com `down` sem remover volumes. O Compose original foi restaurado e permanece com serviços saudáveis. Nenhum banco ou volume de dados foi excluído.

O ensaio foi feito no host de desenvolvimento, seguindo a sequência do guia, e não substitui teste independente por outra pessoa técnica ou avaliação em infraestrutura de produção. Ollama não foi necessário para o fluxo.
