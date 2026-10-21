# Demonstração pública sob demanda, sem custo

Este modo usa Docker local, dados **exclusivamente sintéticos** e Cloudflare
Quick Tunnel. O endereço HTTPS `*.trycloudflare.com` muda a cada execução;
ele só funciona enquanto o computador, o Docker e o comando do túnel estiverem
ativos. Não crie conta paga nem habilite cobrança. O túnel não dá SLA, URL
permanente ou operação contínua. Para hospedagem contínua, mantenha o plano
[Oracle Always Free](demo-oracle-always-free.md) quando houver capacidade A1.

## Pré-requisitos

- Docker Desktop/Engine com Compose recente, Python 3.12+, Git e Node 24 para
  o E2E. Windows PowerShell e Linux são suportados pelo script Python.
- `cloudflared` oficial instalado no PATH. No Windows, use
  `winget install --id Cloudflare.cloudflared --exact`; no Linux, consulte a
  [instalação oficial](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
  Se o executável foi baixado diretamente, defina `CLOUDFLARED_BIN` com seu
  caminho absoluto antes de executar `serve`.
- Conexão de saída HTTPS. Nenhuma porta de entrada precisa ser aberta no
  roteador ou firewall. Os serviços internos não são publicados externamente.

## Preparar e publicar

Execute na raiz do checkout. A preparação cria `.env.quickdemo` privado e
ignorado pelo Git, com cinco segredos hexadecimais distintos. Ela não inicia
containers nem cria URL pública. Não compartilhe esse arquivo.

```powershell
python scripts/quickdemo.py prepare
```

Revise o checkout e confirme que não há dados reais destinados à demonstração.
Quando a exposição pública estiver autorizada:

```powershell
python scripts/quickdemo.py serve
```

O comando abre o túnel, define `WEB_ORIGIN` para a nova URL HTTPS, constrói as
imagens, inicia banco e broker, aplica migrações e provisiona papéis **somente
em volume novo**, sobe os 11 serviços, executa o gate local e valida readiness
na URL pública. Ele imprime a URL após passar esses checks. Se o volume já
existir, o script não migra automaticamente; um upgrade segue o procedimento
de [deploy](deployment.md), com backup prévio. Ele preserva os volumes e os
containers ao receber Ctrl+C, mas fecha a URL pública. Uma nova execução gera
outra URL e recria os serviços com a origem atualizada. Não execute duas
sessões `serve` ao mesmo tempo.

Os volumes pertencem ao projeto `processmind_quickdemo`; a instalação padrão
em `localhost:5173` e seu `.env` não são alterados. A única porta publicada
pelo overlay é `127.0.0.1:5174`, encaminhada ao Nginx. Não abra o host na rede
local nem adicione encaminhamento de portas. `APP_ENV=demo` mantém os cookies
`Secure`. O modelo local é opcional; o endpoint de Ollama no demo aponta a um
serviço indisponível para acionar o fallback explícito, sem API paga.

## Ativar o copiloto com modelo local

No Windows com Docker Desktop, instale o
[Ollama oficial](https://ollama.com/download/windows) no computador do
operador, inicie `ollama serve` e baixe o modelo gratuito já previsto no
projeto. Mantenha o servidor ligado somente em `127.0.0.1:11434`, sem abrir a
porta na rede local ou criar conta de nuvem. Na raiz do projeto:

```powershell
ollama pull gemma3:4b
python scripts/quickdemo.py enable-model
```

`enable-model` consulta o catálogo do Ollama **a partir do container do
model-worker** e só aceita o modelo local `gemma3:4b`. Após a verificação,
atualiza o `.env.quickdemo` privado e recria apenas `model-worker`, com timeout
de 120 segundos para máquinas que executam parte do modelo na CPU. Banco,
uploads, outros serviços e URL pública continuam intactos. O modelo pode usar
vários gigabytes de disco e memória; o download não contém dados da empresa.
O caminho de host `host.docker.internal` desta ativação foi validado no Docker
Desktop; em Linux, mantenha o fallback até haver uma configuração local segura
e validada para acesso ao host.

Para exigir resposta real com citações nos chats normal e temporário, rode o
E2E na URL pública com a variável adicional:

```powershell
$env:E2E_BASE_URL = 'https://URL_IMPRESSA_PELO_SCRIPT'
$env:PROCESSMIND_REQUIRE_MODEL = '1'
Set-Location apps/web
npm run test:e2e
```

O teste normal de CI continua aceitando o fallback porque não baixa o modelo.
Se Ollama não estiver disponível ou o modelo produzir resposta inválida, o
copiloto mostra uma limitação; a auditoria determinística continua funcionando.
Para voltar deliberadamente ao fallback sem apagar conversas:

```powershell
python scripts/quickdemo.py disable-model
```

## Aceite e monitoramento

Com `serve` em execução, valide o fluxo sintético completo em outro terminal:

```powershell
Set-Location apps/web
npm ci
npx playwright install chromium
$env:E2E_BASE_URL = 'https://URL_IMPRESSA_PELO_SCRIPT'
npm run test:e2e
```

O gate `verify_deployment.py` já roda antes de o script anunciar a URL.
Durante a apresentação, confira `docker compose ps` com as opções de projeto e
env abaixo e observe `audit-monitor`. Os logs são locais; não publique logs
brutos se puderem incluir dados da sessão. Não há alerta externo 24/7.

## Backup, restauração e encerramento

Use os [procedimentos de backup e restauração](backup-and-restore.md) com o
mesmo projeto e overlay. No PowerShell, os scripts que chamam `docker compose`
diretamente recebem este contexto:

```powershell
$env:COMPOSE_PROJECT_NAME = 'processmind_quickdemo'
$env:COMPOSE_FILE = 'compose.yaml;compose.quickdemo.yaml'
$env:COMPOSE_ENV_FILES = '.env.quickdemo'
python scripts/backup_local.py --help
```

Antes de fazer backup, confira a sintaxe e a segurança do procedimento no guia
existente. Guarde a cópia em mídia protegida fora do volume Docker e prove a
restauração em projeto isolado. Interrompa a URL com Ctrl+C; para parar também
os containers sem apagar dados:

```powershell
docker compose --project-name processmind_quickdemo --env-file .env.quickdemo -f compose.yaml -f compose.quickdemo.yaml down
```

Nunca use `down -v`, pois isso apagaria banco, uploads e broker. O rollback de
imagem/schema segue [deployment.md](deployment.md); o túnel pode ser encerrado
antes da manutenção. A URL temporária não necessita de rollback remoto.
