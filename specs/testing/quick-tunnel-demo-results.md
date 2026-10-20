# Validação da demonstração sob demanda — 2026-10-20

## Ambiente

- Windows, Docker Compose v5.5.1, `cloudflared` 2026.10.2 assinado pela
  Cloudflare. Binário Windows verificado com o SHA-256 publicado no release.
- Projeto `processmind_quickdemo`, separado da instalação padrão. Somente web
  publicou `127.0.0.1:5174`; volumes de PostgreSQL, RabbitMQ e uploads usam
  prefixo próprio. `.env.quickdemo` ficou fora do Git e com ACL apenas para o
  usuário atual.
- URL HTTPS temporária gerada pelo Quick Tunnel. Ela não é endereço permanente
  nem depende de conta ou pagamento.

## Evidências executadas

1. `docker compose config --quiet` passou com o overlay. A inspeção do Compose
   confirmou a única porta de host e os três volumes isolados.
2. Instalação em banco novo: Alembic, provisionamento de papéis e 11 serviços
   subiram. `verify_deployment.py` retornou `status: ok` para serviços,
   migração, limites dos papéis e despacho da auditoria.
3. `GET /` e `GET /api/v1/health/ready` na URL pública retornaram HTTP 200
   com HTTPS válido.
4. `npm run test:e2e` com `E2E_BASE_URL` pública: **3 passaram (49,8 s)**.
   Cobertura: headers/cache, acessibilidade/navegação e cadastro → organização
   → importação → auditoria → achado → caso → resolução.
5. Scripts: 19 testes unitários passaram; Ruff e mypy do lançador passaram;
   `validate_specs.py` validou 34 paths e 75 referências.

O CI do PR continua sendo o gate para build ARM64, API, browser, carga e
restauração isolada. O teste público não substitui backup fora do computador
nem prova disponibilidade contínua. Ao encerrar o processo `serve`, a URL deixa
de funcionar; uma nova execução gera outra URL e atualiza `WEB_ORIGIN`.
