# Conector de documentação pública do GitHub v1

## Decisão e escopo

O primeiro conector externo lê arquivos Markdown ou texto de repositórios
públicos pelo endpoint oficial de conteúdo do GitHub. O caso inicial autorizado
é `picolitios/processmind-ai`. Owner/Admin cadastra explicitamente repositório,
caminho e título de cada arquivo; nenhuma conta, token, API paga ou credencial
privada é solicitada. O conteúdo é uma **cópia verificada**, identificada pelo
SHA do blob e momento da consulta, não uma promessa de leitura em tempo real.
Arquivos privados, URLs arbitrárias, outros hosts, HTML e binários ficam fora
do escopo. O agente existente continua usando apenas documentos habilitados
do tenant, agora com `source_type=github_public` e proveniência visível.

## Contrato

`POST /api/v1/organizations/{organization_id}/integrations/github-public/documents`
recebe `owner`, `repo`, `path`, `title` e `enabled`. Requer sessão, CSRF e papel
Owner/Admin. O backend valida segmentos ASCII de owner/repo/path, extensão
`.md` ou `.txt`, tamanho e UTF-8; chama somente `api.github.com` por HTTPS,
sem redirecionamento, autenticação ou URL fornecida pelo cliente. A resposta
deve ser arquivo Base64 com SHA de blob válido. Limites: até 20.000 caracteres
de conteúdo, 64 KiB de resposta HTTP, 10 segundos de conexão. A criação
persiste cópia, SHA, origem e data de verificação em `knowledge_sources`, com
evento de auditoria sem conteúdo. Mesmo caminho na mesma empresa retorna 409.

`POST /api/v1/organizations/{organization_id}/integrations/github-public/documents/{source_id}/refresh`
repete a verificação e substitui a cópia somente se o blob mudou; atualiza
revisão e invalida citações anteriores nesse caso. Falha externa não modifica
a cópia. `PATCH /integrations/knowledge/{source_id}` permite título e estado,
mas proíbe alterar manualmente o conteúdo de fonte GitHub. Desabilitar a fonte
impede novas consultas e invalida suas citações. O GET existente mostra tipo,
owner/repo/path, SHA e último check; a página de citação exibe a cópia e um
link identificado como versão atual no GitHub.

Erros: 422 para entrada, arquivo ausente/privado/não textual; 409 para caminho
já registrado; 503 para indisponibilidade ou limite da API; 404 para fonte de
outro tenant. Nenhum erro ou log inclui corpo da resposta remota. O limite
gratuito sem autenticação do GitHub depende do IP e pode atingir 60 chamadas
por hora; a sincronização é manual e não ocorre a cada pergunta. O modelo
recebe somente o trecho autorizado e a citação interna referencia a revisão
persistida. Respostas não declaram que o arquivo está atualizado em tempo real.

## Dados e migração

Migração aditiva: `source_type` com default `managed_knowledge` para linhas
legadas, colunas opcionais `github_owner`, `github_repo`, `github_path`,
`github_blob_sha`, `github_checked_at`, CHECK de proveniência por tipo e índice
único por organização+repositório+caminho. Downgrade recusa fontes GitHub ainda
presentes, para não apagar sua proveniência. Não há FK entre identidade e
negócios. Nenhum segredo novo é necessário.

## Aceite

- Arquivo público válido é importado, consultado pelo agente com citação e
  página de origem; reimportar mesmo caminho retorna 409.
- Caminho inválido, conteúdo binário/grande, repositório privado, redireção,
  timeout e rate limit falham de modo controlado sem criar fonte.
- Refresh sem mudança mantém revisão; com mudança incrementa e invalida
  citação antiga. Desabilitar bloqueia consulta futura.
- Membro de outra empresa não lê, atualiza nem usa a fonte; analista e viewer
  não configuram o conector. CSRF é obrigatório.
- Migração upgrade/downgrade/upgrade em banco descartável, testes Python,
  lint/tipos/build web, E2E Compose e consulta real sintética no GitHub.
