# ProcessMind AI

SaaS B2B de auditoria de compras empresariais. O MVP importa compras, aplica regras verificáveis, organiza achados em casos e usa IA local apenas para explicações ancoradas em evidências.

## Estado

Fases 0 a 4 concluídas. A Fase 4 entrega auditorias determinísticas, achados e evidências na API e no worker local; formulários e telas de negócio integram a Fase 6. Consulte [plano](specs/implementation-plan.md) e [escopo](specs/product/mvp.md).

## Requisitos locais

- Windows com PowerShell, Docker Desktop e Docker Compose;
- Python 3.12 e Node.js 24 para execução e verificações fora dos contêineres;
- serviços gratuitos e locais. Ollama será necessário apenas na Fase 5.

## Documentação

- [Visão](specs/product/vision.md), [requisitos](specs/product/requirements.md) e [MVP](specs/product/mvp.md)
- [Arquitetura](specs/architecture/system-design.md), [modelo de dados](specs/architecture/data-model.md), [stack](specs/architecture/tech-stack.md)
- [Contrato OpenAPI planejado](specs/architecture/openapi.yaml), [segurança](specs/security/security-model.md), [testes](specs/testing/test-strategy.md)
- [Backlog e dependências](specs/implementation-plan.md), [ADRs](specs/decisions/)

O OpenAPI em `specs/` descreve o contrato alvo do MVP; endpoints ainda não implementados não são expostos pelo serviço.

## Fundação local (Fase 1)

No PowerShell, a partir da raiz:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
```

API: `http://localhost:8000/api/v1/health/live` e `/ready`. Web: `http://localhost:5173`. Antes de usar dados reais, substitua a senha local de `.env`; o mesmo valor precisa constar em `DATABASE_URL`. O Docker Desktop deve estar em execução. Para desenvolvimento sem Compose:

```powershell
cd apps/api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e '.[dev]'
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\uvicorn app.main:app --reload
```

Em outro terminal:

```powershell
cd apps/web
npm ci
npm run dev
```

Verificações: `ruff check .`, `mypy app`, `pytest` em `apps/api`; `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build` em `apps/web`. A CI executa migrações e testes com PostgreSQL real. A migration `0001_foundation` é a baseline; as migrações seguintes criam identidade, o índice de retenção de falhas de login e as tabelas de ingestão. Ainda não há interface funcional de auditoria.

## API de identidade (Fase 2)

Os endpoints implementados constam em `/docs` da API e em `specs/architecture/openapi.yaml`. O fluxo é `POST /api/v1/auth/register` → `POST /api/v1/auth/login` → `POST /api/v1/organizations`. O login define um cookie HttpOnly e retorna `csrf_token`; envie esse valor no cabeçalho `X-CSRF-Token` em operações mutáveis autenticadas. O backend confere a associação e o papel em cada operação da organização. `Owner` pode associar usuários já cadastrados por email; convites por email não fazem parte desta fase.

O teste de integração local usa um banco separado. Para criá-lo e executar o gate da Fase 2:

```powershell
docker compose exec -T db psql -U processmind -d postgres -c 'CREATE DATABASE processmind_test'
cd apps/api
$env:DATABASE_URL='postgresql+psycopg://processmind:change-me-local@127.0.0.1:5432/processmind_test'
$env:RUN_DB_TESTS='1'
.\.venv\Scripts\alembic upgrade head
.\.venv\Scripts\pytest
```

Se `processmind_test` já existir, pule apenas o comando `CREATE DATABASE`. Para uso fora do ambiente local, configure `APP_ENV` e uma chave `AUTH_HASH_KEY` aleatória de pelo menos 32 caracteres fora do repositório. O cookie fica `Secure` fora de `APP_ENV=local`.

## Ingestão (Fase 3)

`POST /api/v1/organizations/{id}/imports` recebe `multipart/form-data` com `file` CSV UTF-8 ou XLSX (até 20 MiB por padrão). Requer sessão, CSRF e papel Owner/Admin/Analyst. `Idempotency-Key` opcional evita repetição da mesma requisição. Hash SHA-256 igual na mesma organização retorna conflito; para reimportar, envie `reimport_reason` no formulário. O arquivo original fica em volume privado `upload_data`, fora da pasta pública do web.

Consulte `/imports/{id}/preview` para cabeçalhos e até 20 linhas; confirme em `/imports/{id}/confirm` com `{"columns":{"purchase_id":"coluna_origem", ...}}`. O worker processa até 50 mil linhas, preserva o conteúdo bruto e apresenta erros por linha em `/imports/{id}/rows`. Compras válidas ficam em `/purchases`. O resumo e histórico estão em `/imports` e `/imports/{id}`. Os campos obrigatórios estão no [contrato](specs/architecture/openapi.yaml). Datas usam ISO 8601 (`YYYY-MM-DD`), decimais usam ponto, e moeda usa código de três letras. O worker reinicia jobs interrompidos após expirar o lease; erros permanentes ficam em estado `failed` com código de erro interno no banco.

Depois de atualizar o código, aplique a migração antes de iniciar o worker: `docker compose up -d db api`, `docker compose exec -T api alembic upgrade head`, `docker compose up -d worker web`. Para gerar CSV sintético e gabarito local, execute `python scripts/generate_synthetic.py --size 100 --seed 42 --output-dir synthetic-output` (tamanhos: 100, 1000, 10000, 50000). Acrescente `--xlsx` para gerar também uma planilha com o mesmo gabarito. O diretório de saída é ignorado pelo Git.

## Auditoria determinística (Fase 4)

Crie uma execução com `POST /api/v1/organizations/{id}/audits`, corpo `{"import_ids":["..."]}` e cabeçalhos `X-CSRF-Token` e `Idempotency-Key` (8–128 caracteres). Apenas importações concluídas da organização são aceitas. Owner/Admin/Analyst criam auditorias; Viewer consulta. O worker aplica as [nove regras versionadas](specs/architecture/audit-rules-v1.md) usando o snapshot da configuração, sem depender de IA.

Consulte `/audits`, `/audits/{id}`, `/findings` e `/findings/{id}` para estado, filtros, achados e evidências. As listagens usam cursor e limite de até 100 itens. Preço sem cinco pares comparáveis fica inconclusivo; o resumo da execução informa a limitação. O [relatório de avaliação](specs/testing/audit-evaluation.md) traz TP/FP/FN para os quatro tamanhos sintéticos e pode ser reproduzido por `python scripts/evaluate_audit.py --sizes 100 1000 10000 50000 --seed 42 --assert-gates` com o ambiente Python da API. Revisão de achados e casos pertencem à Fase 6.

## Explicações opcionais com IA (Fase 5)

Configure um Ollama local e baixe o modelo indicado em `OLLAMA_MODEL` (padrão `gemma3:4b`). No Compose, o worker acessa `OLLAMA_BASE_URL=http://host.docker.internal:11434`; fora do Compose, use `http://127.0.0.1:11434`. `OLLAMA_TIMEOUT_SECONDS` controla o tempo máximo por análise. A auditoria funciona mesmo sem Ollama.

Depois de uma auditoria concluída, envie `POST /api/v1/organizations/{id}/ai/analyses` com `{"finding_id":"..."}` ou `{"audit_id":"..."}`, sessão, CSRF e `Idempotency-Key`. A resposta contém `analysis_id`; consulte `GET /ai/analyses/{analysis_id}`. Resultados citam apenas IDs presentes nas evidências dos achados; falhas retornam `status=failed` e `limitation`, sem modificar a auditoria. Consulte os [limites e critérios](specs/architecture/ai-explanations-v1.md).

## Casos e indicadores (Fase 6, API)

`PATCH /findings/{id}` registra revisão direta quando não há caso. `POST /cases` abre um único caso por achado; `PATCH /cases/{id}` muda estado ou responsável, com justificativa obrigatória ao encerrar. `GET /cases/{id}` mostra histórico e comentários recentes; `/cases/{id}/comments` lista todos por cursor e recebe novos comentários. `GET /analytics/overview` traz contagens, evolução e rankings com filtros `from`/`to`. Como a importação não possui categoria, o ranking de categorias permanece vazio e o de produtos é exibido com limitação explícita. As [transições e definições dos indicadores](specs/architecture/cases-and-analytics-v1.md) são parte do contrato. A interface completa dessas operações está em desenvolvimento na Fase 6.
