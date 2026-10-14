# Requisitos e critérios de aceite

IDs estáveis permitem rastrear backlog, testes e contratos. `M` indica MVP; `N` indica requisito não funcional. M01–M03 estão implementados na API desde a Fase 2; as telas correspondentes continuam planejadas para a Fase 6. Os demais requisitos permanecem planejados conforme o backlog.

| ID | Requisito | Critério de aceite observável |
| --- | --- | --- |
| M01 | Cadastro, login, logout e sessão | Credenciais inválidas não criam sessão; logout revoga a sessão; cookie não é acessível por JS; tentativas excessivas são limitadas. |
| M02 | Organizações, usuários e RBAC | Owner gerencia membros; Admin gerencia operações; Analyst audita e revisa; Viewer só lê; falta de papel retorna 403, e recurso de outra organização retorna 404. |
| M03 | Isolamento | IDs de outra organização não revelam nem modificam dados, inclusive em listagens, detalhes, jobs e analytics; testes automatizados cobrem dois tenants. |
| M04 | Upload CSV/XLSX | Arquivo dentro dos limites, formato válido e cabeçalhos mapeáveis gera importação; arquivo inválido recebe erro seguro; hash evita duplicação acidental na organização. |
| M05 | Prévia, mapeamento e validação | Usuário confirma mapeamento antes da ingestão; erros por linha/campo são consultáveis; linhas inválidas não se tornam compras; original e normalizado permanecem rastreáveis. |
| M06 | Auditoria determinística | As nove regras listadas abaixo produzem achados com versão, severidade, evidência e justificativa; reprocessamento não duplica achados da mesma execução. |
| M07 | Estatística | Preço atípico usa pares comparáveis e mediana/IQR/MAD; amostra insuficiente mostra limitação, nunca marca fraude. |
| M08 | IA local | Resposta validada por schema cita apenas achados/evidências recebidos; indisponibilidade de Ollama não impede auditoria e é mostrada claramente. |
| M09 | Alertas e casos | Achado pode ser revisado e virar um caso; transições válidas registram ator/data; encerramento exige justificativa; comentários preservam histórico. |
| M10 | Dashboard | Indicadores, evolução e rankings são derivados do banco, respeitam filtros/tenant, têm paginação e estados vazio/erro/carregamento. |
| M11 | Trilha | Eventos de login, importação, auditoria, configuração, permissões, casos e fechamento são persistidos sem segredos. |
| M12 | UI pt-BR | Onze telas do prompt são navegáveis, responsivas, acessíveis por teclado e apresentam feedback de erro/sucesso. |
| M13 | Dados sintéticos | Semente fixa gera 100, 1k, 10k e 50k linhas com gabarito de duplicidade, preço, atraso, inválidos e normais. |
| N01 | Local e gratuito | Compose inicia os serviços sem dependência de serviço pago; comandos PowerShell documentados e executáveis. |
| N02 | Qualidade | TS strict, Python tipado, lint, typecheck, testes e CI passam nas fases pertinentes. |
| N03 | Segurança | Entrada validada, SQL parametrizado, CSRF, limites de upload, timeouts, proteção contra abuso e logs sem dados sensíveis. |
| N04 | Observabilidade | Logs JSON com correlação e métricas de job; health distingue liveness e readiness. |
| N05 | Contrato | API `/api/v1`, erros padronizados, paginação estável, filtros/ordenação permitidos e OpenAPI sincronizado. |

## Regras de auditoria (M06)

| Código | Condição inicial | Evidência / borda |
| --- | --- | --- |
| DUPLICATE | Mesma organização, fornecedor, produto, data, quantidade e valor em compras distintas; ID de compra repetido é erro de importação | IDs envolvidos; compras legítimas repetidas exigem revisão humana. |
| TOTAL_MISMATCH | `abs(total_amount - quantity * unit_price) > 0.01` na moeda do registro | Valores decimais e diferença; sem conversão cambial. |
| INVALID_QUANTITY | Quantidade menor ou igual a zero | Valor original; linha inválida pode ser achado de qualidade sem Purchase persistida. |
| PRICE_OUTLIER | Preço fora de limite configurado ou faixa estatística entre pares comparáveis | Mediana, dispersão, tamanho e filtro da amostra; sem grupo suficiente, resultado inconclusivo. |
| INVALID_DATES | Entrega anterior à compra ou entrega real sem expectativa coerente | Datas de origem; data futura isolada não prova erro. |
| LATE_DELIVERY | Entrega real posterior à prevista | Dias de atraso; entrega ainda pendente requer estado explícito, não atraso realizado. |
| RECURRING_DELAY | Fornecedor com pelo menos 3 entregas concluídas e ao menos 50% atrasadas no período configurado | Numerador, denominador e período; limiares configuráveis. |
| INCOMPLETE_RECORD | Falta de campo obrigatório ou dado não analisável | Campo e linha; não inventar valor. |
| OVER_LIMIT | `total_amount` supera limite da organização na mesma moeda | Limite e valor; sem limite configurado, regra não se aplica. |

Valores acima são defaults iniciais e devem ser versionados com cada execução. Comparações de preço usam mesmo `product_id`, moeda e unidade; como a lista inicial não contém unidade, a Fase 3 deverá adicionar `unit_of_measure` opcional e excluir pares sem equivalência de unidade comprovada. Janela padrão: 90 dias; mínimo estatístico: 5 compras válidas de outros registros. Prazos e severidades ficam configuráveis e documentados no motor.

## Dados de entrada

Obrigatórios para compra analisável: `purchase_id`, `supplier_id`, `purchase_date`, `product_id`, `quantity`, `unit_price`, `currency`; `total_amount` é obrigatório para checar inconsistência entre valor declarado e calculado. `supplier_name` e `product_name` são descrições opcionais. `expected_delivery_date` e `actual_delivery_date` são opcionais. `unit_of_measure` é opcional, mas preço não é comparável sem unidade comum. `calculated_total` é derivado e nunca substitui o valor declarado. Valores monetários usam Decimal, ISO 4217 e escala por moeda definida no processamento.

## Telas do MVP

Login/cadastro; criação de organização; dashboard; importações; assistente de importação; histórico de auditorias; detalhe de auditoria; central de alertas; detalhe de alerta; casos; configurações da organização e usuários. Telas dependentes de funcionalidade aparecem quando esta fase estiver implementada, com operação real e estados completos.
