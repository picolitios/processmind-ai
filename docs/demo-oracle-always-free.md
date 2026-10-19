# Demonstração pública na Oracle Always Free

Estado: **preparada no repositório, ainda não publicada**. A criação/alteração de
recursos externos requer autorização específica do proprietário. Este guia
mantém o limite obrigatório de R$ 0 e usa apenas dados sintéticos. Confirme no
console Oracle que cada recurso mostra o selo **Always Free** e que a conta não
foi atualizada para Pay As You Go. Capacidade ARM livre pode não existir na região
escolhida. Não use créditos de avaliação para contornar esse limite.

## Compatibilidade e topologia

Render Free não executa esta instalação completa: não oferece worker gratuito
nem disco persistente, e seu PostgreSQL gratuito tem prazo. A VM ARM Always
Free comporta como hipótese a instalação Compose de host único, mas capacidade
real, ociosidade, I/O e fluxo de navegador só podem ser confirmados na VM.
Ollama fica desativado inicialmente; análises e copiloto mostram o fallback
existente. Uma avaliação posterior pode ativar um modelo pequeno local após
medir memória/latência, sem API paga.

`compose.yaml` conserva PostgreSQL, RabbitMQ, uploads e o certificado Caddy em
volumes Docker no disco persistente da VM. `compose.demo.yaml` publica somente
80/443 por Caddy. As portas de banco, broker, API, identidade e web continuam
presas a `127.0.0.1` no host. Não exponha 5432, 5672, 15672, 8000, 8001 ou
5173 no firewall. O endereço público exige um hostname DNS sob controle do
proprietário; `onrender.com` não pertence a uma VM Oracle. Um subdomínio gratuito
é aceitável se puder apontar para o IP público e permanecer estável.

## Pré-requisitos externos, após autorização

1. Conta Oracle no plano Free sem Pay As You Go; VM Ubuntu ARM64 com recursos
   marcados Always Free, disco persistente dentro da cota, IP público e regras
   de entrada TCP 80/443. Limite SSH ao operador sempre que possível. Configure
   atualizações de segurança e um usuário de deploy sem root, com Docker e Git.
2. Hostname DNS com A/AAAA correto. Caddy precisa de entrada 80/443 para emitir
   e renovar HTTPS. Verifique a resolução e a porta antes de iniciar.
3. Clone público em `/opt/processmind` sob o usuário de deploy. Instale Docker
   Engine com plugin Compose, Python 3 e Git. Acesso ao socket Docker equivale
   a privilégios administrativos na VM: dedique essa conta ao deploy e proteja
   sua chave SSH. Confirme imagens ARM64 no CI.
4. Copie `infra/demo/env.example` para `/opt/processmind/.env`. Preencha
   `DEMO_HOST` e `WEB_ORIGIN=https://<mesmo-host>`. Gere separadamente cada
   senha/`AUTH_HASH_KEY` com `openssl rand -hex 32`. Use só caracteres hex nas
   senhas embutidas em URLs SQLAlchemy. `chmod 600 .env`, mantenha o diretório
   de deploy e a chave SSH restritos. Nunca cole `.env` em issue, log ou PR.
5. No GitHub, crie o ambiente `demo` com revisor obrigatório, os segredos
   `DEMO_SSH_PRIVATE_KEY`, `DEMO_SSH_KNOWN_HOSTS`, `DEMO_SSH_HOST` e
   `DEMO_SSH_USER`; capture `known_hosts` por canal verificado, não aceite
   `ssh-keyscan` sem conferir fingerprint. Defina a variável de repositório
   `DEMO_HOST`. Deixe `DEMO_DEPLOY_ENABLED` ausente durante o bootstrap e até a
   autorização específica para a automação externa.

## Instalação inicial

Na VM, a primeira subida é explícita; o workflow automatiza atualizações de um
ambiente já saudável. Execute no commit da `main` que passou CI:

```bash
cd /opt/processmind
docker compose -f compose.yaml -f compose.demo.yaml config --quiet
docker compose up -d --wait db rabbitmq
docker compose build db-admin api identity identity-config-reconciler worker model-worker audit-publisher audit-consumer audit-monitor web
docker compose run --rm --no-deps db-admin alembic upgrade head
docker compose run --rm --no-deps db-admin python -m app.db.provision_roles
docker compose -f compose.yaml -f compose.demo.yaml up -d --no-build --wait --wait-timeout 180
python3 scripts/verify_deployment.py
curl --fail --silent --show-error https://SEU_HOST/api/v1/health/ready
```

O Caddy deve obter certificado válido; não use `curl -k`. O preflight verifica
os 11 serviços persistentes, revisão do banco, limites de credenciais e filas.
Inspecione `docker compose ps`, `docker compose logs --tail 100 caddy` e
`docker compose logs --tail 100 audit-monitor` sem publicar dados sensíveis.
Monitoramento básico: saúde dos containers, preflight, prontidão HTTPS e alerta
local do audit-monitor. Sem serviço externo pago, a observação e resposta são
do operador; não há promessa de alerta 24/7.

## Atualização automática após CI

O workflow `deploy-demo.yml` reage somente ao sucesso do workflow `CI` para um
commit da `main` do próprio repositório. Exige `DEMO_DEPLOY_ENABLED=true`,
ambiente `demo` protegido e segredos SSH. A chave do servidor fica em
`known_hosts`; SSH não aceita host novo silenciosamente. O usuário de deploy
executa `scripts/deploy_demo.sh SHA HOST`: confere checkout, preflight, para
escritores, aguarda trabalho de auditoria, cria/verifica backup, constrói ARM64,
aplica Alembic, provisiona papéis, sobe Compose, verifica saúde local e HTTPS.
O workflow então roda o E2E Playwright na URL pública com dados sintéticos.
Dados de teste podem acumular-se; a demonstração não aceita dados reais.

Se houver trabalho pendente, falha de backup ou de saúde, o workflow falha. O
script reinicia a versão anterior somente antes de iniciar a migração. Depois
disso, não tenta downgrade nem restauração automática. A publicação inicial e
a ativação da variável são ações externas e exigem autorização do usuário.

## Backup, restauração e rollback

Antes de cada atualização, o script cria `backups/demo-<UTC>-<commit>` no disco
da VM e verifica seus hashes. Faça também uma cópia protegida fora da VM, por
exemplo download criptografado para o computador do operador, sem serviços
pagos. Backups no mesmo disco não resistem à perda da VM. O arquivo inclui
PostgreSQL e uploads; `rabbitmq_data` não é restaurado porque o backup exige
filas auditadas e vazias. Não compartilhe a cópia nem credenciais.

Para validar restauração, use [o procedimento isolado](backup-and-restore.md)
com volumes novos e o mesmo commit do arquivo. Após restauração, execute
`verify_deployment.py` e o E2E contra a instalação isolada. O CI já restaura
banco e uploads em destino descartável e compara bytes e referências.

Se a falha ocorreu **antes** da migração, o script volta ao checkout e aos
containers anteriores. Se ocorreu **após** iniciar a migração, preserve logs e
backup, identifique a revisão Alembic e siga as notas da migração. Um rollback
de imagem só é permitido se a revisão anterior for compatível. Caso contrário,
restaure o backup em volumes **novos** e promova a instalação recuperada após
validar; nunca restaure sobre o banco/volume vivo. Para uma demo descartável,
recriar a VM e restaurar a cópia externa é preferível a manipular dados em
produção. Nenhuma meta de RPO/RTO de produção foi estabelecida.

## Aceite público pendente

- HTTPS válido e `/api/v1/health/ready` responde 200; portas administrativas
  não são acessíveis externamente.
- CI, construção ARM64, preflight na VM e E2E público passam.
- Fluxo sintético: cadastro, organização, importação, auditoria, achado, caso,
  atribuição, comentário, resolução e indicador; chats normal/temporário têm
  comportamento de fallback explícito se o modelo local não estiver ativo.
- Cópia fora da VM e restauração isolada do backup são verificadas.

Até executar esses passos na URL real, o produto não está validado como
demonstração pública funcional.
