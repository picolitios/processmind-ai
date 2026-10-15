# Instalação local do MVP

## Pré-requisitos

- Windows com PowerShell e Docker Desktop com Docker Compose ativo.
- Portas locais `5432`, `8000` e `5173` disponíveis.
- Para executar testes fora dos contêineres: Python 3.12 e Node.js 24. O uso normal via Compose não exige essas instalações.

## Primeira execução

No PowerShell, na raiz do repositório:

```powershell
Copy-Item .env.example .env
```

Edite `.env` antes de iniciar os serviços. Defina `POSTGRES_PASSWORD` com uma senha local própria e use o mesmo valor na URL `DATABASE_URL`. Defina `AUTH_HASH_KEY` com uma string aleatória de pelo menos 32 caracteres. Mantenha `.env` fora do Git. `APP_ENV=local` é apropriado apenas para avaliação local.

```powershell
docker compose up -d --build db api
docker compose exec -T api alembic upgrade head
docker compose up -d --build worker web
docker compose ps
```

O banco deve aparecer como saudável antes da migração; API e web devem aparecer como saudáveis depois de iniciar. Abra:

- Interface: <http://localhost:5173>
- Saúde da API: <http://localhost:8000/api/v1/health/ready>
- OpenAPI interativo: <http://localhost:8000/docs>
- Contrato versionado: [`specs/architecture/openapi.yaml`](../specs/architecture/openapi.yaml)

Se o banco ainda estiver inicializando, espere o healthcheck e repita somente o comando que falhou. Execute migrações novamente após atualizar o código, antes de reiniciar o worker. Não use `docker compose down -v` em uma instalação que contenha dados a preservar.

## Parar e retomar

`docker compose stop` interrompe os serviços e mantém os volumes. `docker compose start` os retoma. `docker compose down` remove contêineres e rede, mantendo os volumes. Uploads e PostgreSQL residem em volumes do Compose.

## IA opcional

A importação, auditoria, casos e indicadores funcionam sem Ollama. Para habilitar explicações, instale e inicie Ollama no host e disponibilize o modelo definido em `OLLAMA_MODEL` no `.env`. O worker usa `OLLAMA_BASE_URL` para acessá-lo. Quando indisponível, a interface informa a limitação; as regras determinísticas continuam funcionando.

## Validação automatizada

Com o Compose ativo, em `apps/web`: `npm ci`, `npx playwright install chromium`, `npm run test:e2e`. O E2E cria seus próprios dados de teste no banco em uso. Para testes Python de integração, use um banco PostgreSQL de teste separado e novo, configure `DATABASE_URL` e `RUN_DB_TESTS=1`, aplique `alembic upgrade head` e execute `pytest` em `apps/api`.

O relato de instalação em volumes isolados, com migração e E2E, está em [`specs/testing/phase8-delivery.md`](../specs/testing/phase8-delivery.md).
