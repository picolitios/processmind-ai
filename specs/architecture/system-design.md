# Desenho do sistema

## Limites

SPA React chama API REST FastAPI. API e worker compartilham serviços de domínio e PostgreSQL; o worker processa jobs persistidos. Arquivos originais ficam fora do diretório público e são acessados apenas pela API autenticada. Ollama só é chamado pelo worker de IA. O banco é a fonte de verdade para compras, regras, achados, casos e trilha.

```text
Browser --cookie+CSRF--> API /api/v1 --> PostgreSQL
                           |                 ^
                           +--> arquivo      | jobs/resultado
                           +--> worker -------+
                                  +--> Ollama (opcional)
```

## Módulos de domínio

`identity`: usuário, organização, associação, sessão e RBAC. `ingestion`: upload, mapeamento, validação, arquivo e compras. `audit`: regras determinísticas, anomalias, execução e evidências. `ai`: prompts delimitados, validação da resposta e fallback. `cases`: estado, atribuição e comentários. `analytics`: consultas agregadas. `audit_trail`: eventos append-only. Dependências comuns ficam em `core` (configuração, erros, correlação) e `db` (sessão e migrations). Um módulo não acessa tabelas de outro diretamente fora de serviços/repositórios acordados.

## Fluxo de importação

Upload com limite de bytes e detecção de tipo → hash SHA-256 e arquivo privado temporário → prévia limitada → mapeamento confirmado → job de validação/normalização → `ImportRow` com erro ou `Purchase` → resumo e evento. CSV tem codificação e delimitador explícitos na prévia. XLSX é lido em modo de streaming, sem macros/fórmulas executadas. Arquivo original é movido para armazenamento final apenas após registro persistente; reconciliação detecta órfãos. Mesmo hash+organização gera conflito por padrão, com reimportação explícita e motivo.

## Fluxo de auditoria

API cria `AuditRun` idempotente para importações selecionadas e versão de regras → worker lê compras e erros de `ImportRow` do tenant → aplica regras por lotes → grava achados/evidências e métricas em transação → marca sucesso ou falha. Assim, registros incompletos e quantidades inválidas continuam auditáveis mesmo quando não geram `Purchase`. Achado tem identidade estável por execução, regra e registros envolvidos; revisão humana altera estado, sem apagar evidência. Análise de IA é job separado e pode falhar sem reverter achados.

## Consistência e isolamento

Todos os recursos empresariais carregam `organization_id`; referências entre eles usam chaves compostas ou validação transacional de tenant, além dos filtros obrigatórios. Paginação por `created_at, id` com cursor opaco para coleções grandes. `organization_id` do path é cotejado com associação ativa da sessão. Recurso inexistente ou de outro tenant retorna 404 nos detalhes para evitar enumeração; falta de papel no tenant autenticado retorna 403.

## Jobs e operação

Tabela `job` com tipo, estado, payload validado, chave idempotente, tentativas, lease, timestamps e erro sanitizado. Worker com `FOR UPDATE SKIP LOCKED`, heartbeat/lease e retentativa limitada para falhas transitórias; falhas permanentes ficam visíveis para reprocessamento explícito. Nenhuma thread de requisição executa 50 mil linhas de modo síncrono. `/health/live` verifica processo; `/health/ready` verifica banco. Correlação propagada entre requisição e job; logs JSON sem conteúdo de compras.

## Contratos

`openapi.yaml` documenta a API alvo do MVP. Implementações futuras devem atualizar contrato e schema gerado pelo FastAPI na mesma mudança. Recursos ainda não entregues não ganham rotas decorativas.
