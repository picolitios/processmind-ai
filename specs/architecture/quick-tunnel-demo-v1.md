# Demonstração sob demanda por Cloudflare Quick Tunnel v1

## Escopo e decisão

Enquanto a VM Oracle Always Free estiver sem capacidade em São Paulo, a
demonstração pública pode executar sob demanda no Docker do operador. O
`cloudflared` encaminha um hostname HTTPS aleatório `*.trycloudflare.com`
somente para o Nginx do projeto em `127.0.0.1:5174`. Não há conta Cloudflare,
DNS, API paga nem alteração da infraestrutura Oracle. A URL e a disponibilidade
duram somente enquanto o túnel e o computador estiverem ativos. Este modo é
para avaliação com dados sintéticos, sem SLA ou promessa de URL estável.

## Isolamento e segurança

- Um projeto Compose exclusivo (`processmind_quickdemo`) mantém PostgreSQL,
  RabbitMQ e uploads em volumes próprios. Não usa o `.env` nem os volumes da
  instalação local atual. Só o Nginx recebe porta de host, em loopback.
- O operador gera segredos únicos e fortes em `.env.quickdemo`, ignorado pelo
  Git. O arquivo nunca é impresso em log. `APP_ENV=demo` mantém cookies seguros;
  `WEB_ORIGIN` precisa corresponder à URL HTTPS atual do túnel.
- O túnel deve usar somente a interface web; banco, broker, API e identidade
  não têm portas de host no overlay. O serviço de modelo usa fallback local
  explícito quando não há Ollama; nenhuma API paga é necessária.
- O operador autoriza a exposição pública e testa somente dados sintéticos.
  O script para o túnel ao receber Ctrl+C, mas preserva volumes e containers.

## Fluxo

1. Preparar/validar o arquivo privado de ambiente e o Compose isolado.
2. Construir imagens, iniciar banco e broker, aplicar Alembic e provisionar
   papéis em instalação nova; em instalação existente, não repetir mudanças de
   schema automaticamente. Iniciar serviços e executar o gate local.
3. Abrir o Quick Tunnel, obter hostname, definir `WEB_ORIGIN` e recriar os
   serviços que dependem dele. Verificar HTTPS e executar E2E sintético.
4. Encerrar túnel quando a apresentação terminar. Para reiniciar, obter nova
   URL e atualizar a origem. Backup, restauração isolada e rollback seguem os
   guias existentes, sempre com o projeto Compose exclusivo.

## Aceite

1. `docker compose config --quiet` valida o overlay; apenas a web publica
   `127.0.0.1:5174`. Volumes têm prefixo exclusivo.
2. Uma instalação nova migra banco, provisiona papéis, sobe os 11 serviços e
   passa `verify_deployment.py`, sem tocar na instalação local existente.
3. A URL pública apresenta HTTPS válido, readiness e E2E completo com dados
   sintéticos. Não se afirma esse aceite antes do teste real.
4. Os scripts de backup/restauração existentes podem ser usados com o mesmo
   ambiente e projeto isolado. Interromper o túnel não remove dados.
5. CI existente permanece ativo; sem cobrança ou segredo versionado.
