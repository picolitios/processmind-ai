# Modelo local para a demonstração do copiloto v1

## Decisão

Ativar o contrato do copiloto V2 já implementado usando Ollama gratuito no
computador do operador. O modelo inicial é `gemma3:4b`, existente na
configuração padrão do projeto. O servidor Ollama escuta apenas em
`127.0.0.1:11434`; no Docker Desktop, `model-worker` acessa o host por
`host.docker.internal` no Docker Desktop para Windows. O navegador público não
acessa Ollama diretamente. Linux conserva o fallback até existir um caminho de
rede local equivalente e validado sem publicar a porta do Ollama.
Nenhuma API externa de inferência, assinatura ou cobrança é usada. Os dados
enviados ao modelo são os contextos sintéticos delimitados pela spec V2.

## Ativação e falha

- A demo recém-criada conserva o fallback explícito. A ativação é comando
  separado, após instalar Ollama, obter o modelo local e verificar que o
  container alcança `/api/tags` no host. O comando aceita apenas o endpoint
  local `http://host.docker.internal:11434` e o tag local aprovado, sem
  possibilidade de trocar silenciosamente por `:cloud` ou API paga.
- A ativação muda somente `.env.quickdemo` privado e recria `model-worker`,
  preservando banco, uploads, sessões e a URL atual. O timeout do modelo pode
  chegar a 120 segundos em CPU; job e interface mantêm estados de processamento
  e erro. A desativação retorna ao fallback sem apagar chats.
- A ausência de Ollama/modelo, falha de rede ou resposta inválida mantém a
  limitação explícita. Auditorias e casos determinísticos continuam funcionais.
  Respostas só são publicadas com IDs de evidência validados pelo servidor.

## Aceite

1. Ollama responde localmente, com porta 11434 ligada apenas ao loopback.
2. `model-worker` alcança Ollama; modelo local consta em `/api/tags`.
3. Um prompt sintético no contrato JSON gera resposta e IDs de evidência
   válidos dentro de 120 segundos, ou a limitação é registrada sem fingir
   sucesso.
4. E2E público opcional exige resposta real e citações navegáveis nos chats
   normal e temporário. CI sem modelo continua validando fallback.
5. Desativação, reinício e rollback estão documentados; nenhum segredo ou
   prompt integral é registrado no Git ou em logs.
