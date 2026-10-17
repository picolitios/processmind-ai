# Modelo de dados lógico (PostgreSQL)

Todas as PKs são UUID, timestamps são `timestamptz` UTC, quantidades e dinheiro são `numeric` (sem float). Campos `created_at` e `updated_at` existem nas entidades mutáveis; eventos e evidências são append-only. `organization_id` é obrigatório em toda entidade de negócio, inclusive jobs e análises. UUIDs não substituem autorização.

As tabelas `User`, `Organization`, `OrganizationConfigCommand`, `OrganizationMembership`, `Session`, `LoginFailure` e `AuditEvent` pertencem ao schema `identity`. As demais entidades pertencem a `business`. A tabela técnica `alembic_version` permanece em `public`; apenas a credencial administrativa executa DDL e reconciliação entre schemas. Os papéis de runtime não têm privilégios no schema do outro domínio.

| Entidade | Campos principais e relacionamentos | Constraints e índices essenciais |
| --- | --- | --- |
| User | email normalizado, password_hash, status | email único global; índice por status |
| Organization | name, slug, status, settings_version | slug único; configurações versionadas |
| AuditConfiguration | organization_id, settings_version, last_command_id, amount_limits, delay_window_days | Uma linha por organização; apenas a auditoria aplica versões no modo coordenado; comando repetido é verificado por ID e conteúdo |
| OrganizationConfigCommand | id, organization_id, settings_version, kind, amount_limits, delay_window_days, status, created/updated/applied_at | Comando durável da identidade; único `(organization_id,settings_version)`; índice status/data; pendência recuperável e conflito explícito |
| OrganizationMembership | organization_id, user_id, role, status | FK para ambos; único `(organization_id,user_id)`; role enum |
| Session | user_id, token_hash, csrf_hash, expires_at, revoked_at | token_hash único; índice `(user_id,expires_at)`; retenção limitada |
| LoginFailure | HMAC do email, HMAC do IP, occurred_at | índices por email/data, IP/data e data para expurgo; sem credenciais em claro |
| ImportBatch | organization_id, uploader_id, sha256, original_name, private_storage_key, mapping, status, counts, idempotency_key, reimport_reason | conflito por hash é serializado por organização na API; reimportação exige motivo; único `(organization_id,idempotency_key)` quando informado; índice `(organization_id,created_at,id)` |
| ImportRow | organization_id, batch_id, row_number, raw_json, normalized_json, errors | FK composta para batch; único `(batch_id,row_number)`; raw com acesso restrito |
| Supplier | organization_id, external_id, name | único `(organization_id,external_id)` |
| Purchase | organization_id, batch_id, import_row_id, supplier_id, external_purchase_id, product_id/name, purchase_date, quantity, unit_of_measure, unit_price, declared_total, currency, expected/actual_delivery_date | FKs compostas; `import_row_id` único; índices por produto/data, fornecedor/data e batch. IDs externos repetidos são preservados e sinalizados. |
| AuditRun | organization_id, requester_id, status, rule_set_version, config_snapshot, import_ids, finding_count, limitation, started/finished_at, job_id, idempotency_key | único `(organization_id,idempotency_key)`; FK composta para job; índice tenant/data |
| AuditRule | code, version, enabled_by_default, parameter_schema | único `(code,version)`; catálogo global imutável por versão |
| AuditFinding | organization_id, run_id, rule_code/version, severity, review_state, explanation, detected_at, fingerprint | FK para run e rule; único `(organization_id,run_id,fingerprint)`; índice por severidade/estado/data |
| FindingEvidence | organization_id, finding_id, purchase_id nullable, import_row_id nullable, evidence_json | FK composta para finding e referências do mesmo tenant; ao menos um vínculo de origem |
| AuditCase | organization_id, finding_id, assignee_membership_id nullable, status, closure_reason, opened/closed_at | FK composta; um caso por finding em todo o histórico; índice status/responsável/data |
| CaseComment | organization_id, case_id, author_membership_id, body | FK composta; índice case/data; sem edição silenciosa |
| AuditEvent | organization_id nullable para login pré-organização, actor_user_id nullable, action, subject_type/id, metadata allowlisted, correlation_id, occurred_at | append-only; índices tenant/data, subject/data; retenção definida |
| BusinessAuditEvent | id, organization_id, actor_user_id nullable, action, subject_type/id, metadata_json, correlation_id, occurred_at | trilha append-only de ações de negócios; cópia legada temporária para rollback; sem FK para identidade |
| AIAnalysis | organization_id, run_id nullable, finding_id nullable, model/version, schema_version, response_json, status, evidence_hash | FK composta; referência a run ou finding; índice status/data |
| Job | organization_id, type, status, payload_json, idempotency_key, attempt_count, lease_until, error_code | único `(organization_id,type,idempotency_key)`; índice `(status,lease_until)`; importação usa `idempotency_key = ImportBatch.id` para vínculo um a um |
| OutboxEvent | organization_id, event_type/version, envelope, created_at, published_at | UUID de organização validado pela identidade no pedido, sem FK entre schemas; índice parcial de eventos não publicados por data; a criação da auditoria persiste job e evento na mesma transação |

## Integridade e retenção

FKs compostas `(organization_id,id)` exigem `UNIQUE (organization_id,id)` na tabela pai. Membros e usuários são desativados, não excluídos em cascata. Compras, importações e achados usam exclusão lógica/retention controlada para manter trilha; exclusão física de dados empresariais requer fluxo administrativo futuro e política legal definida. Arquivos originais e `raw_json` contêm dados potencialmente sensíveis, com acesso restrito e backup local protegido. `AuditEvent` e evidências não são mutados. Migrations Alembic são a única fonte de DDL e devem ter upgrade/downgrade não destrutivos quando possível.

## Questões deliberadas para fases posteriores

Política legal de retenção e exclusão de dados depende do ambiente real de uso; até defini-la, não oferecer botão de apagamento nem prometer retenção infinita. Uso inicial é local e controlado. RLS pode reforçar o isolamento após a autorização da aplicação estar coberta por testes.
