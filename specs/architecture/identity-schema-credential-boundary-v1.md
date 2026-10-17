# Isolamento de schemas e credenciais v1

Status: incremento reversível da Fase 2. Depende da reconciliação limpa e do corte das FKs entre identidade e negócios em `identity-reference-fk-cutover-v1.md`.

## Decisão e escopo

- Manter uma instância PostgreSQL e um banco. Mover as sete tabelas da identidade para o schema `identity` e as quinze tabelas de negócios para `business`, sem copiar ou modificar linhas. `public.alembic_version` permanece sob a credencial de migração.
- Criar papéis de runtime `processmind_identity` e `processmind_business`, sem propriedade nem DDL. Cada papel recebe apenas `USAGE` e DML no seu schema. A credencial administrativa existente permanece exclusiva para migração e reconciliação operacional, nunca nos processos de runtime do Compose.
- Os papéis começam `NOLOGIN`. Um passo de provisionamento recebe senhas por variáveis de ambiente e habilita LOGIN, sem registrá-las. O Compose exige senhas distintas e usa o respectivo papel em API, workers e identidade.
- `BUSINESS_AUTH_MODE=identity`, `AUDIT_CONFIG_MODE=owned`, `AUDIT_CONFIG_WRITE_MODE=coordinated` e `BUSINESS_EVENT_WRITE_MODE=owned` são obrigatórios nesse arranjo. A API de negócios não monta rotas de identidade nesse modo. Os modos de banco compartilhado continuam disponíveis apenas para rollback com a credencial administrativa.
- A reconciliação entre domínios é executada somente pela credencial de migração, encontra tabelas em ambos os schemas e continua aceitando o layout legado `public` para downgrade.

## Operação e rollback

1. Parar todos os escritores. Com credencial administrativa, exigir reconciliação de referências e eventos limpa; drenar comandos de configuração. Aplicar a migração transacional, provisionar senhas e reiniciar serviços com as credenciais separadas.
2. Exigir que cada credencial de runtime conecte, leia e escreva apenas suas próprias tabelas; `SELECT`, `INSERT`, `UPDATE` e `DELETE` em tabelas do outro schema devem falhar. Verificar APIs, fluxos entre tenants, E2E e reconciliação pós-migração.
3. Para rollback, parar os serviços, configurar temporariamente a credencial administrativa, executar downgrade e só então reativar a versão antiga. O downgrade move as tabelas de volta, preserva as linhas e remove os privilégios dos papéis separados. As cópias legadas de configuração e eventos seguem os gates dos runbooks existentes.

## Critérios de aceite

- Contagens e UUIDs das tabelas preservados no upgrade, downgrade e novo upgrade.
- Nenhuma credencial de runtime permite acesso a tabelas do outro domínio nem a `public.alembic_version`.
- API de negócios em modo identidade não expõe rotas de login, sessão, usuários ou criação de organização.
- Reconciliação dos 20 vínculos e testes de integração passam antes/depois; isolamento de tenant e snapshot de configuração permanecem válidos.
- Falha de identidade/configuração continua fechada, sem consulta direta às tabelas privadas do outro domínio.

## Fora do escopo

Banco físico separado, política de exclusão de identidades, remoção dos modos de rollback e mudanças no contrato público de `/api/v1`.
