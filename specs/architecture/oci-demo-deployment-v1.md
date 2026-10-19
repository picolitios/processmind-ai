# Demonstração externa em Oracle Always Free v1

## Decisão e limites

Preparar o Compose existente para uma única VM Linux ARM64 da camada Oracle
Always Free. O orçamento de implantação e operação é R$ 0: nenhuma API paga,
upgrade Pay As You Go ou recurso fora da franquia Always Free. O ambiente usa
somente dados sintéticos e não possui SLA, RPO ou RTO de produção. A criação de
conta, VM, DNS, segredos, regras de rede e a primeira publicação dependem de
autorização específica do usuário. A automação versionada permanece inerte até
que a variável protegida `DEMO_DEPLOY_ENABLED=true` seja configurada.

Render Free não é alvo de execução completa: a ausência de worker e de disco
persistente gratuitos e o prazo do banco gratuito não atendem esta arquitetura.
O hostname público não pode ser `onrender.com` em uma VM Oracle; será informado
por `DEMO_HOST` e deve resolver para o IP público antes de emitir certificado.

## Topologia

- Caddy recebe 80/443, obtém TLS e encaminha à interface Nginx; Nginx mantém
  o roteamento de identidade/API. Apenas 80/443 e SSH entram no firewall da VM.
- PostgreSQL, RabbitMQ, API, identidade, workers, monitor e uploads permanecem
  no Compose. Volumes Docker persistem no disco da VM, inclusive certificados.
- `.env` é local, privado e não versionado. CI/GitHub armazena apenas a chave SSH
  de deploy, host, usuário e chave pública de host para uma conta sem root.
- `APP_ENV=demo` ativa cookie `Secure`; `WEB_ORIGIN` deve ser exatamente
  `https://<DEMO_HOST>`. Nunca usar credenciais padrão da `.env.example`.
- Ollama é opcional e local à VM. A publicação inicial não depende de modelo;
  falhas de modelo mantêm o fallback explícito previsto na spec do copiloto.

## Publicação

O workflow de deploy observa CI concluído com sucesso em `main`, mas só executa
com `DEMO_DEPLOY_ENABLED=true` em ambiente GitHub `demo` protegido. Executa no
host um commit SHA da `main` validado. Antes de migrar, para escritores, drena
auditoria e produz backup consistente. Falha no drain ou backup interrompe a
publicação. Migrações Alembic e provisionamento de papéis ocorrem antes de
reiniciar a aplicação. O preflight local e a verificação HTTPS externa precisam
passar. O E2E de navegador usa somente contas e dados sintéticos.

Um erro após migração não aciona downgrade ou restauração automática. O operador
segue o runbook de rollback após avaliar a migração aplicada. Backups contêm
dados sensíveis mesmo quando sintéticos; ficam fora do Git e exigem cópia
protegida fora da VM para sobreviver à perda da instância.

## Aceite

1. `docker compose -f compose.yaml -f compose.demo.yaml config` é válido em
   ARM64; apenas Caddy publica portas de rede externas.
2. CI existente de API, web, broker, E2E, carga e restauração permanece ativo;
   uma construção ARM64 de API e web passa no CI.
3. O deploy não inicia sem variável explícita, CI verde, ambiente protegido,
   segredos SSH e host conhecido. Nenhum segredo de aplicação vai ao log/Git.
4. A instalação nova aplica migrações versionadas, inicia serviços com volumes
   persistentes e passa `verify_deployment.py`; o bootstrap automatiza a
   sequência e recusa volumes existentes, segredos fracos ou checkout sujo.
5. Na URL pública, HTTPS, saúde e E2E completo passam com dados sintéticos.
6. Backup, restauração isolada e rollback estão documentados e são exercidos
   antes de chamar o ambiente de demonstração funcional.

Até a autorização e existência da VM/hostname, os itens 4–6 são pendências de
validação externa; testes locais/CI não os substituem.
