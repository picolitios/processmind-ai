# Escopo do MVP

## Dentro do escopo

Autenticação e organização; importação segura de compras; nove regras de auditoria; estatística robusta com amostra e contexto explícitos; explicação opcional via Ollama; dashboard derivado de dados persistidos; revisão de achados, casos e trilha de auditoria. As telas obrigatórias estão listadas em `requirements.md`.

## Fora do escopo

RH, contabilidade, estoque, contratos, integração ERP, notificações, regras personalizadas, exportação de relatórios, cobrança, agentes autônomos, previsão e detecção por Isolation Forest. Preparar interfaces internas para evolução não autoriza implementar esses recursos.

## Sequência

Fase 0: contrato e plano. Fase 1: fundação executável. Fase 2: identidade e isolamento. Fase 3: importação. Fase 4: auditoria e estatística. Fase 5: IA. Fase 6: interface e casos. Fase 7: estabilização. Fase 8: entrega. Cada fase tem critérios próprios no plano.

## Critério final

O fluxo cadastro → organização → importação → auditoria → achado → caso → resolução funciona de ponta a ponta com dados sintéticos reproduzíveis, sem serviços pagos, com testes de isolamento e documentação de execução.
