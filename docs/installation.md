# Instalação local do MVP

## Pré-requisitos

- Windows com PowerShell e Docker Desktop com Docker Compose ativo.
- Portas locais `5432`, `5672`, `15672`, `8000`, `8001` e `5173` disponíveis.
- Para executar testes fora dos contêineres: Python 3.12 e Node.js 24. O uso normal via Compose não exige essas instalações.

## Primeira execução

No PowerShell, na raiz do repositório:

```powershell
Copy-Item .env.example .env
```

Edite `.env` antes de iniciar os serviços. Defina `POSTGRES_PASSWORD` com uma senha local própria e use o mesmo valor na URL `DATABASE_URL`. Defina `AUTH_HASH_KEY` com uma string aleatória de pelo menos 32 caracteres. Mantenha `.env` fora do Git. `APP_ENV=local` é apropriado apenas para avaliação local.

```powershell
docker compose up -d db rabbitmq
docker compose build api identity worker audit-publisher audit-consumer web
docker compose run --rm --no-deps api alembic upgrade head
docker compose up -d --no-build api identity worker audit-publisher audit-consumer web
docker compose ps
```

O banco deve aparecer como saudável antes da migração; API e web devem aparecer como saudáveis depois de iniciar. Abra:

- Interface: <http://localhost:5173>
- Saúde da API: <http://localhost:8000/api/v1/health/ready>
- Saúde da identidade: <http://localhost:8001/api/v1/health/ready>
- OpenAPI interativo: <http://localhost:8000/docs>
- Contrato versionado: [`specs/architecture/openapi.yaml`](../specs/architecture/openapi.yaml)

Se o banco ainda estiver inicializando, espere o healthcheck e repita somente o comando que falhou. Execute migrações novamente após atualizar o código, antes de reiniciar o worker. Não use `docker compose down -v` em uma instalação que contenha dados a preservar.

Para **atualizar uma instalação existente**, termine primeiro os jobs de auditoria antigos em modo `database`. Pare API e identidade durante a cópia para impedir PATCH com o código antigo entre o backfill e a ativação da gravação sincronizada. Em seguida, construa as imagens e aplique a migração aditiva com um contêiner temporário:

```powershell
docker compose stop api identity
docker compose build api identity worker audit-publisher audit-consumer web
docker compose run --rm --no-deps api alembic upgrade head
```

Antes de ativar a leitura `AUDIT_CONFIG_MODE=owned` em uma instalação existente, compare a contagem das duas tabelas e procure divergências de versão e valores. As contagens devem ser iguais e a segunda consulta deve retornar `0`; execute-as após a migração e antes de recriar a API. O Compose já seleciona `owned` para a API. Em caso de divergência, retome a imagem anterior e investigue a cópia. Para rollback de leitura, selecione `AUDIT_CONFIG_MODE=legacy` e retenha ambas as tabelas.

```sql
SELECT (SELECT count(*) FROM organizations) AS organizations,
       (SELECT count(*) FROM audit_configurations) AS audit_configurations;

SELECT count(*) FROM organizations o
LEFT JOIN audit_configurations a ON a.organization_id = o.id
WHERE a.organization_id IS NULL
   OR a.settings_version IS DISTINCT FROM o.settings_version
   OR a.amount_limits IS DISTINCT FROM
      CASE WHEN o.settings ? 'amount_limits' THEN o.settings->'amount_limits'
           ELSE '{}'::jsonb END
   OR a.delay_window_days IS DISTINCT FROM
      CASE WHEN o.settings ? 'delay_window_days'
           THEN (o.settings->>'delay_window_days')::integer ELSE 90 END;
```

Após a verificação, recrie os serviços:

```powershell
docker compose up -d --no-build rabbitmq api identity worker audit-publisher audit-consumer web
```

O nginx resolve novamente o endereço da API após a recriação do contêiner.

O nginx envia `/api/v1/auth/*` e as rotas de organização, configurações e membros para o processo de identidade. Importações, auditorias, achados, IA, casos e indicadores continuam na API de negócios. Ambos usam o mesmo PostgreSQL nesta etapa transitória; a [spec do limite de identidade](../specs/architecture/identity-boundary-v1.md) registra o alcance e as pendências de propriedade dos dados.

Auditorias novas usam a outbox e RabbitMQ em Compose. `http://localhost:15672` mostra o broker local. A API persiste o pedido mesmo quando o broker estiver indisponível; o publicador retoma a entrega quando a conexão voltar. O worker antigo continua importação e IA. Antes de ativar o modo `broker` em uma instalação antiga, conclua as auditorias ainda enfileiradas em modo `database` (veja `docs/architecture/migration-plan.md`).

## Parar e retomar

`docker compose stop` interrompe os serviços e mantém os volumes. `docker compose start` os retoma. `docker compose down` remove contêineres e rede, mantendo os volumes. Uploads e PostgreSQL residem em volumes do Compose.

## IA opcional

A importação, auditoria, casos e indicadores funcionam sem Ollama. Para habilitar explicações, instale e inicie Ollama no host e disponibilize o modelo definido em `OLLAMA_MODEL` no `.env`. O worker usa `OLLAMA_BASE_URL` para acessá-lo. Quando indisponível, a interface informa a limitação; as regras determinísticas continuam funcionando.

## Validação automatizada

Com o Compose ativo, em `apps/web`: `npm ci`, `npx playwright install chromium`, `npm run test:e2e`. O E2E cria seus próprios dados de teste no banco em uso. Para testes Python de integração, use um banco PostgreSQL de teste separado e novo, configure `DATABASE_URL` e `RUN_DB_TESTS=1`, aplique `alembic upgrade head` e execute `pytest` em `apps/api`.

O relato de instalação em volumes isolados, com migração e E2E, está em [`specs/testing/phase8-delivery.md`](../specs/testing/phase8-delivery.md).
