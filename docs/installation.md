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

Edite `.env` antes de iniciar os serviços. Defina `POSTGRES_PASSWORD` com uma senha local própria e use o mesmo valor na URL administrativa `DATABASE_URL`. Defina `IDENTITY_DB_PASSWORD` e `BUSINESS_DB_PASSWORD` com valores aleatórios distintos de pelo menos 32 caracteres; eles não devem conter caracteres de URL sem codificação. Defina `AUTH_HASH_KEY` com uma string aleatória de pelo menos 32 caracteres. Mantenha `.env` fora do Git. `APP_ENV=local` é apropriado apenas para avaliação local.

```powershell
docker compose up -d db rabbitmq
docker compose build db-admin api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose run --rm --no-deps db-admin alembic upgrade head
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose up -d --no-build api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose ps
```

O banco deve aparecer como saudável antes da migração; API e web devem aparecer como saudáveis depois de iniciar. Abra:

- Interface: <http://localhost:5173>
- Saúde da API: <http://localhost:8000/api/v1/health/ready>
- Saúde da identidade: <http://localhost:8001/api/v1/health/ready>
- OpenAPI interativo: <http://localhost:8000/docs>
- Contrato versionado: [`specs/architecture/openapi.yaml`](../specs/architecture/openapi.yaml)

Se o banco ainda estiver inicializando, espere o healthcheck e repita somente o comando que falhou. Execute migrações novamente após atualizar o código, antes de reiniciar o worker. Não use `docker compose down -v` em uma instalação que contenha dados a preservar.

Para **atualizar uma instalação existente**, termine primeiro os jobs de auditoria antigos em modo `database`. Execute os gates de reconciliação descritos abaixo com a credencial administrativa e exija resultados limpos e `pending=blocked=0`. Anote as contagens das tabelas relevantes. Construa as imagens, pare todos os escritores e aplique a migração transacional com `db-admin`. Este serviço está no perfil `tools` e não inicia com `docker compose up` normal:

```powershell
docker compose build db-admin api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose run --rm --no-deps db-admin python -m app.db.reconcile_identity
docker compose run --rm --no-deps db-admin python -m app.db.reconcile_business_events
docker compose run --rm --no-deps db-admin python -m app.features.identity.config_sync report
docker compose stop web api identity identity-config-reconciler worker model-worker audit-consumer audit-publisher audit-monitor
docker compose run --rm --no-deps db-admin alembic upgrade head
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose run --rm --no-deps db-admin python -m app.db.reconcile_identity
docker compose run --rm --no-deps api python -m app.db.verify_role_boundary
docker compose run --rm --no-deps identity python -m app.db.verify_role_boundary
```

Antes de ativar a leitura `AUDIT_CONFIG_MODE=owned` em uma instalação existente, compare a contagem das duas tabelas e procure divergências de versão e valores. As contagens devem ser iguais e a segunda consulta deve retornar `0`; execute-as após a migração e antes de recriar a API. O Compose já seleciona `owned` para a API. O modo de escrita coordenada exige essa leitura; para rollback no banco compartilhado, selecione `AUDIT_CONFIG_WRITE_MODE=database` junto de `AUDIT_CONFIG_MODE=legacy` e retenha ambas as tabelas.

O mesmo gate vale para `AUDIT_CONFIG_WRITE_MODE=coordinated`: a contagem e a consulta SQL abaixo devem confirmar cópias iguais antes da primeira ativação. O Compose usa `coordinated` na identidade e na API de compatibilidade. Se a auditoria estiver indisponível, criação/alteração de organização retorna `503`; o comando persiste e `identity-config-reconciler` tenta novamente. Inspecione as pendências sem expor valores de configuração:

```powershell
docker compose run --rm --no-deps db-admin python -m app.features.identity.config_sync report
```

Antes de voltar para `AUDIT_CONFIG_WRITE_MODE=database` ou para uma imagem antiga, mantenha o reconciliador ativo até `pending=0`, resolva qualquer `blocked` e repita a comparação SQL. Para localizar uma pendência sem ler seus valores, consulte `SELECT organization_id, settings_version, status FROM organization_config_commands WHERE status <> 'applied'`. Um comando `blocked` indica conflito que exige investigação; não sincronize versões por sobrescrita manual. Uma criação que retornou `503` pode ser repetida pelo mesmo owner com o mesmo slug e nome, retornando a organização provisionada.

Antes de ativar `BUSINESS_EVENT_WRITE_MODE=owned` na API, no worker e no consumidor, execute a reconciliação abaixo com os escritores parados. Exija `status=clean` e `owned_only=legacy_only=conflicts=0`. Se houver divergência, mantenha `BUSINESS_EVENT_WRITE_MODE=dual` e investigue. O Compose seleciona `owned` após essa verificação; para uma instalação que ainda não passou pelo gate, defina `BUSINESS_EVENT_WRITE_MODE=dual` no `.env` até concluí-lo.

```powershell
docker compose run --rm --no-deps db-admin python -m app.db.reconcile_business_events
```

Se o código antigo processar alterações durante um rollback, repita uma reconciliação revisada das duas cópias antes de reativar a versão nova. A migração Alembic já aplicada não repete automaticamente o backfill.

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

Se precisar voltar à imagem anterior depois de operar em `owned`, pare API, worker e consumidor; execute `docker compose run --rm --no-deps db-admin python -m app.db.reconcile_business_events --restore-legacy` antes de reiniciar a imagem antiga. Exija as três contagens de divergência zeradas após a restauração. O comando só adiciona cópias ausentes; nunca corrige conteúdo conflitante automaticamente.

Após a verificação, recrie os serviços:

```powershell
docker compose up -d --no-build rabbitmq api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
```

O nginx resolve novamente o endereço da API após a recriação do contêiner.

O nginx envia `/api/v1/auth/*` e as rotas de organização, configurações e membros para o processo de identidade. Importações, auditorias, achados, IA, casos e indicadores continuam na API de negócios. Ambos usam o mesmo PostgreSQL com schemas e papéis separados; a [spec do corte](../specs/architecture/identity-schema-credential-boundary-v1.md) registra o alcance e o rollback.

Para desfazer o corte, pare todos os serviços Python, use a credencial administrativa de `db-admin` e execute `docker compose run --rm --no-deps db-admin alembic downgrade 6fd3a81b29c4`. A migração devolve as tabelas a `public` sem apagar linhas. Antes de iniciar uma imagem antiga, restaure suas variáveis de modo e credencial administrativa e cumpra os gates de cópias legadas acima. Os papéis globais permanecem no cluster porque outro banco pode usá-los, mas perdem acesso aos schemas deste banco.

Auditorias novas usam a outbox e RabbitMQ em Compose. `http://localhost:15672` mostra o broker local. A API persiste o pedido mesmo quando o broker estiver indisponível; o publicador retoma a entrega quando a conexão voltar. `worker` executa importações; `model-worker` executa explicações e copiloto, inclusive a limpeza de chats temporários. Ambos usam a mesma tabela de jobs e banco de negócios. Antes de ativar o modo `broker` em uma instalação antiga, conclua as auditorias ainda enfileiradas em modo `database` (veja `docs/architecture/migration-plan.md`).

`audit-monitor` consulta a outbox, os jobs de auditoria e as quatro filas a cada 60 segundos. `docker compose ps audit-monitor` mostra `healthy` somente após uma amostra válida sem atraso na outbox ou em jobs enfileirados, lease vencido ou mensagem na DLQ. `docker compose logs audit-monitor` registra somente mudanças de estado, sem dados de empresas. Para investigar, execute o comando de diagnóstico descrito no README; a configuração de intervalo e limite de atraso está em `.env.example`. Uma marcação `unhealthy` é um sinal operacional e não reinicia automaticamente o publicador ou o consumidor.

## Parar e retomar

`docker compose stop` interrompe os serviços e mantém os volumes. `docker compose start` os retoma. `docker compose down` remove contêineres e rede, mantendo os volumes. Uploads e PostgreSQL residem em volumes do Compose.

Os serviços persistentes usam `restart: unless-stopped` para voltar após falhas de processo ou reinício do Docker. Se você os interromper intencionalmente com `docker compose stop`, retome-os com `docker compose start` ou `docker compose up -d --no-build`; a política de reinício respeita a parada manual. Após reiniciar o Docker, confirme `docker compose ps` e os healthchecks antes de usar a interface. Esse mecanismo não substitui backup nem alta disponibilidade.

## IA opcional

A importação, auditoria, casos e indicadores funcionam sem Ollama. Para habilitar explicações e respostas do copiloto, instale e inicie Ollama no host e disponibilize o modelo definido em `OLLAMA_MODEL` no `.env`. `model-worker` usa `OLLAMA_BASE_URL` para acessá-lo. Quando indisponível, a interface informa a limitação; as regras determinísticas continuam funcionando.

## Validação automatizada

Com o Compose ativo, em `apps/web`: `npm ci`, `npx playwright install chromium`, `npm run test:e2e`. O E2E cria seus próprios dados de teste no banco em uso. Para testes Python de integração, use um banco PostgreSQL de teste separado e novo, configure `DATABASE_URL` e `RUN_DB_TESTS=1`, aplique `alembic upgrade head` e execute `pytest` em `apps/api`.

O CI executa o Playwright Chromium em um Compose isolado, com credenciais de teste geradas durante o job, migrações e papéis de banco provisionados antes da abertura da interface. O gate é definido em `.github/workflows/ci.yml` e especificado em [`specs/testing/browser-ci-v1.md`](../specs/testing/browser-ci-v1.md).

Antes de qualquer migração futura que remova FKs entre identidade e negócios, execute a reconciliação somente de leitura com a imagem da API atualizada:

```powershell
docker compose run --rm --no-deps db-admin python -m app.db.reconcile_identity
```

O comando retorna JSON sem dados pessoais individuais. Código de saída `0` indica referências consistentes naquele retrato, `2` indica inconsistência e `1` falha técnica. O [relatório local](architecture/reference-reconciliation-2026-10-16.md) registra o resultado deste incremento; ele não substitui os contratos e a política de exclusão exigidos antes de remover FKs.

O relato de instalação em volumes isolados, com migração e E2E, está em [`specs/testing/phase8-delivery.md`](../specs/testing/phase8-delivery.md).
