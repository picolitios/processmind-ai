# Modelo de segurança

## Ativos e fronteiras

Ativos: credenciais, sessões, arquivos originais, compras, evidências, decisões e configurações. Fronteiras: navegador/API; API/banco; API/armazenamento privado; worker/Ollama. Dados importados e saída de LLM são não confiáveis. Ameaças principais: acesso entre tenants, roubo de sessão, CSRF, força bruta, upload malicioso, prompt injection, negação de serviço e vazamento por logs/erros.

## Controles obrigatórios

- Senhas com Argon2id, salt e política de tamanho; verificação do hash mesmo para conta ausente. Cinco falhas por conta em 15 minutos bloqueiam novas tentativas; falhas antigas são removidas após um dia. A chave HMAC para indexar contas no throttle é configurada fora do Git em produção. Mensagens de login não enumeram usuários.
- Sessão opaca com token aleatório forte, apenas hash no banco, rotação após autenticação, expiração e revogação no logout. Cookie HttpOnly, SameSite=Lax, Path limitado e Secure fora de desenvolvimento local.
- Mutação autenticada exige token CSRF associado à sessão e checagem de Origin; CORS restrito à origem web configurada. Não usar wildcard com credenciais.
- RBAC no backend por associação ativa e organização explícita; ID do cliente jamais concede acesso. Testar IDs diretos, paginação, downloads, jobs, analytics e relações indiretas entre tenants.
- No Compose, identidade e negócios usam credenciais PostgreSQL distintas, sem DDL e com DML apenas no próprio schema. A credencial administrativa é reservada a migrações e reconciliação executadas sob demanda; cada papel de runtime deve falhar ao tentar SELECT, INSERT, UPDATE ou DELETE no outro domínio.
- Upload com tamanho máximo configurável (padrão 20 MiB), limites de linhas (50 mil), colunas, células e descompressão; extensão, assinatura e parser validados. Não executar macro, fórmula, HTML ou comando; nome original nunca vira caminho do sistema. XLSX zip bomb e CSV formula injection são tratados, inclusive em qualquer exportação futura.
- SQLAlchemy parametriza consultas; strings de filtro/ordem usam allowlist. Respostas exibidas no frontend são escapadas pelo React; CSP e headers de segurança são configurados na entrega web.
- Job tem limites de tempo, tentativas e concorrência por organização. Ollama tem timeout e circuito de falha; contexto só inclui evidências permitidas, delimitadas como dados, com IDs conferidos após resposta.
- Logs estruturados registram IDs, ação, resultado e código de erro, sem senha, cookie, linha bruta, prompt integral ou resposta sensível. Erros públicos têm código estável e correlation ID; detalhes internos ficam em log protegido.
- Segredos ficam em variáveis de ambiente fora do Git; `.env.example` não contém valores reais. Banco e diretório de upload não são expostos publicamente na implantação.

## Autorização inicial

| Operação | Owner | Admin | Analyst | Viewer |
| --- | --- | --- | --- | --- |
| Gerenciar membros/papéis | sim | não | não | não |
| Configurar limites operacionais | sim | sim | não | não |
| Importar dados / executar auditoria | sim | sim | sim | não |
| Revisar achado / gerir caso | sim | sim | sim | não |
| Consultar dados autorizados | sim | sim | sim | sim |

## Riscos residuais e gates

No modo local, segurança do host e backups permanecem responsabilidade operacional; a documentação de entrega deverá instruir permissões de filesystem e backup. A proteção de dados pessoais requer avaliação antes de produção real. Gate da Fase 2: testes de isolamento e CSRF. Gate da Fase 3: corpus de uploads adversariais. Gate da Fase 5: prompt injection e validação de referências. Gate da Fase 7: revisão de headers, limites, carga e dependências.
