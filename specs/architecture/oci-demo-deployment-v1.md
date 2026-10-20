# Demonstração externa em Oracle Always Free v1

## Decisão e limites

Preparar o Compose existente para uma única VM Linux ARM64 da camada Oracle
Always Free. O orçamento de implantação e operação é R$ 0: nenhuma API paga,
upgrade Pay As You Go ou recurso fora da franquia Always Free. O ambiente usa
somente dados sintéticos e não possui SLA, RPO ou RTO de produção. A criação de
conta, VM, DNS, segredos, regras de rede e a primeira publicação dependem de
autorização específica do usuário. A automação versionada permanece inerte até
que seu timer seja instalado após o primeiro bootstrap saudável.

Render Free não é alvo de execução completa: a ausência de worker e de disco
persistente gratuitos e o prazo do banco gratuito não atendem esta arquitetura.
O hostname público não pode ser `onrender.com` em uma VM Oracle; será informado
por `DEMO_HOST` e deve resolver para o IP público antes de emitir certificado.

## Topologia

- Caddy recebe 80/443, obtém TLS e encaminha à interface Nginx; Nginx mantém
  o roteamento de identidade/API. Apenas 80/443 e SSH entram no firewall da VM.
- PostgreSQL, RabbitMQ, API, identidade, workers, monitor e uploads permanecem
  no Compose. Volumes Docker persistem no disco da VM, inclusive certificados.
- `.env` é local, privado e não versionado. A VM consulta a API pública do
  GitHub sem token e não recebe uma chave de deploy pelo workflow.
- `APP_ENV=demo` ativa cookie `Secure`; `WEB_ORIGIN` deve ser exatamente
  `https://<DEMO_HOST>`. Nunca usar credenciais padrão da `.env.example`.
- Ollama é opcional e local à VM. A publicação inicial não depende de modelo;
  falhas de modelo mantêm o fallback explícito previsto na spec do copiloto.

## Publicação

Um timer local, instalado somente após bootstrap e autorização, consulta a API
pública do GitHub por conexão de saída a cada dez minutos. Ele compara o SHA do
último run de push bem-sucedido do workflow `CI` com o head remoto de `main` no
repositório exato. Sem correspondência, não executa deploy. O verificador fica
fora do checkout e executa como o usuário dedicado `processmind`, com acesso ao
Docker; não recebe token do GitHub. O repositório público não recebe runner
self-hosted persistente, conforme o risco descrito na
[orientação do GitHub](https://docs.github.com/en/actions/reference/security/secure-use).
O host executa o commit SHA validado. Antes de migrar, para escritores, drena
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
3. O timer permanece desativado até instalação explícita após o bootstrap. O
   deploy não inicia sem CI verde para o head exato da `main`; o serviço não
   precisa abrir SSH para o GitHub nem guardar token de API. Nenhum segredo de
   aplicação vai ao log/Git.
4. A instalação nova aplica migrações versionadas, inicia serviços com volumes
   persistentes e passa `verify_deployment.py`; o bootstrap automatiza a
   sequência e recusa volumes existentes, segredos fracos ou checkout sujo.
5. Na URL pública, HTTPS, saúde e E2E completo passam com dados sintéticos.
6. Backup, restauração isolada e rollback estão documentados e são exercidos
   antes de chamar o ambiente de demonstração funcional.

Em 2026-10-20, a rede Always Free de São Paulo já estava criada e a OCI voltou
a retornar `Out of capacity` para A1 2 OCPU/12 GB. A tentativa de 1 OCPU/6 GB
recebeu o mesmo erro em AD-1; a de 1 OCPU/8 GB havia falhado anteriormente.
Não há VM nem hostname público. Os itens 4–6 continuam pendentes de validação
externa; testes locais/CI não os substituem. A regra SSH permanece limitada ao
operador.
O timer de deploy só poderá ser instalado e exercido quando existir a VM
Always Free.
