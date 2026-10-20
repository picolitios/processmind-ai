# Demonstração pública na Oracle Always Free

Estado em 2026-10-19: **rede criada, VM e aplicação ainda não publicadas**.
Na conta Free Tier `victorxapn`, região São Paulo, a VCN
`processmind-demo-vcn` e a subnet pública `processmind-demo-public` estão
disponíveis. O gateway de internet e a rota `0.0.0.0/0` estão ativos. A lista
de segurança admite 80/443 de qualquer origem e 22 somente do IPv4 atual do
operador. A Oracle recusou a VM A1 de 2 OCPU/12 GB e também a de 1 OCPU/8 GB
por falta de capacidade no único domínio de disponibilidade exibido (`AD-1`).
Nenhuma VM foi criada. Não use forma paga, crédito de avaliação ou upgrade
para contornar essa limitação. A criação/alteração de recursos externos requer
autorização específica do proprietário. Este guia
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
   Quando houver capacidade A1, revise a mesma rede, o selo Always Free, o
   disco e as regras antes de criar a VM.
2. Hostname DNS com A/AAAA correto. Caddy precisa de entrada 80/443 para emitir
   e renovar HTTPS. Verifique a resolução e a porta antes de iniciar.
3. Prepare uma VM Ubuntu 24.04 ARM64 com o script versionado abaixo. Ele
   instala Docker Engine e o plugin Compose do repositório oficial, Python 3 e
   Git, ativa atualizações de segurança, cria o usuário `processmind` sem sudo,
   instala uma chave pública Ed25519 e clona a `main` em `/opt/processmind`.
   Acesso ao socket Docker equivale
   a privilégios administrativos na VM: dedique essa conta ao deploy e proteja
   sua chave SSH. Confirme imagens ARM64 no CI. Transfira somente o script e a
   chave **pública**, nunca a privada; ajuste o IPv4 abaixo ao IP real da VM:

   ```bash
   scp -i ~/.ssh/processmind_oci_demo_ed25519 scripts/provision_demo_host.sh ~/.ssh/processmind_oci_demo_ed25519.pub ubuntu@IP_DA_VM:/home/ubuntu/
   ssh -i ~/.ssh/processmind_oci_demo_ed25519 ubuntu@IP_DA_VM 'sudo bash /home/ubuntu/provision_demo_host.sh /home/ubuntu/processmind_oci_demo_ed25519.pub'
   ```

   O script recusa outro sistema/arquitetura, chave inválida e checkout já
   existente com origem diferente. Sua repetição preserva `.env`, dados e
   commit instalado. Confira a fingerprint SSH da VM por canal verificado
   antes da primeira conexão; não aceite uma chave desconhecida às cegas.
4. Copie `infra/demo/env.example` para `/opt/processmind/.env`. Preencha
   `DEMO_HOST` e `WEB_ORIGIN=https://<mesmo-host>`. Gere separadamente cada
   senha/`AUTH_HASH_KEY` com `openssl rand -hex 32`. Use só caracteres hex nas
   senhas embutidas em URLs SQLAlchemy. `chmod 600 .env`, mantenha o diretório
   de deploy e a chave SSH restritos. Nunca cole `.env` em issue, log ou PR.
5. Mantenha SSH/22 limitado ao IP do operador. O deploy automático usa um
   timer na própria VM que consulta a API pública do GitHub e o ref remoto
   `main`, ambos por conexões de saída. Ele só chama o deploy quando o commit
   atual de `main` corresponde ao último run de push concluído com sucesso no
   workflow `CI`. Não há runner self-hosted, token do GitHub nem segredo SSH
   no workflow. A [orientação de segurança do GitHub](https://docs.github.com/en/actions/reference/security/secure-use)
   desaconselha runners persistentes em repositórios públicos. O timer é
   instalado somente após o primeiro bootstrap validado e autorizado.

## Instalação inicial

Na VM, o bootstrap é explícito; o timer automatiza atualizações de um
ambiente já saudável. Conecte-se como `processmind` com a mesma chave e execute
no commit da `main` que passou CI:

```bash
cd /opt/processmind
bash scripts/bootstrap_demo.sh SEU_HOST
```

O script recusa checkout sujo, segredos fracos/reutilizados, `.env` público,
containers ou volumes existentes. Se uma instalação parcial falhar, preserve
seus volumes e investigue antes de repetir; o script não apaga dados. O Caddy
deve obter certificado válido; não use `curl -k`. O preflight verifica
os 11 serviços persistentes, revisão do banco, limites de credenciais e filas.
Inspecione `docker compose ps`, `docker compose logs --tail 100 caddy` e
`docker compose logs --tail 100 audit-monitor` sem publicar dados sensíveis.
Monitoramento básico: saúde dos containers, preflight, prontidão HTTPS e alerta
local do audit-monitor. Sem serviço externo pago, a observação e resposta são
do operador; não há promessa de alerta 24/7.

Após o primeiro fluxo sintético completo e a verificação de backup, conecte-se
como `ubuntu` e ative o timer, usando o hostname público já validado:

```bash
sudo bash /opt/processmind/scripts/install_demo_poller.sh SEU_HOST
systemctl status processmind-demo-deploy.timer
journalctl -u processmind-demo-deploy.service -n 50 --no-pager
```

O instalador exige `.env` privado e pertencente a `processmind`; ele copia o
verificador para fora do checkout e configura uma execução a cada dez minutos
com pequeno atraso aleatório. A VM só precisa de saída HTTPS/443 para o GitHub.
Se a API estiver indisponível ou o CI falhar, não há deploy. Pare o timer com
`sudo systemctl disable --now processmind-demo-deploy.timer` antes de manutenção
manual; nenhuma migração ou rollback ocorre só por parar o timer.

## Atualização automática após CI

`scripts/poll_demo_deploy.py` consulta no GitHub o último run de push em `main`
e compara seu SHA ao head remoto de `main`. Só com conclusão `success` e
repositório exato ele executa `scripts/deploy_demo.sh SHA HOST` como usuário
`processmind`. O deploy confere checkout, preflight, para
escritores, aguarda trabalho de auditoria, cria/verifica backup, constrói ARM64,
aplica Alembic, provisiona papéis, sobe Compose, verifica saúde local e HTTPS.
Após cada publicação, execute o E2E Playwright na URL pública com dados
sintéticos (veja o aceite abaixo). Dados de teste podem acumular-se; a
demonstração não aceita dados reais.

No computador de desenvolvimento com Node.js 24, valide pelo PowerShell:

```powershell
Set-Location apps/web
npm ci
npx playwright install chromium
$env:E2E_BASE_URL = 'https://SEU_HOST'
npm run test:e2e
```

Se houver trabalho pendente, falha de backup ou de saúde, o serviço falha. O
script reinicia a versão anterior somente antes de iniciar a migração. Depois
disso, não tenta downgrade nem restauração automática. A publicação inicial e
a ativação do timer são ações externas e exigem autorização do usuário.

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
- O timer instala e executa apenas um SHA de `main` com CI de push bem-sucedido;
  o journal registra falhas e não contém segredos.
- Fluxo sintético: cadastro, organização, importação, auditoria, achado, caso,
  atribuição, comentário, resolução e indicador; chats normal/temporário têm
  comportamento de fallback explícito se o modelo local não estiver ativo.
- Cópia fora da VM e restauração isolada do backup são verificadas.

Até executar esses passos na URL real, o produto não está validado como
demonstração pública funcional.
