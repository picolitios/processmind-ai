# Versão 2 — copiloto selecionado

O MVP das Fases 0–8 está integrado. O usuário escolheu **copiloto conversacional** como primeira entrega funcional da Versão 2. O contrato fechado para esse incremento está em [`copilot-v2.md`](../architecture/copilot-v2.md). Cada chat parte de um achado ou auditoria. O modo temporário usa somente o histórico do próprio chat. Por padrão, conversas normais são salvas e podem compor a memória da empresa; Owner/Admin podem configurar modo temporário por padrão, exigindo aprovação para Analyst salvar uma conversa. O modo normal pode usar conversas e evidências de outros alvos da mesma organização com citações e controle de acesso.

## Outras candidatas para entregas futuras

| Entrega | Base existente | Decisão de produto necessária | Principal risco |
| --- | --- | --- | --- |
| Relatórios exportáveis | Indicadores, auditorias, achados e casos persistidos | Conteúdo, formato (CSV/PDF), filtros e público dos relatórios | Vazamento de dados e injeção de fórmula em CSV |
| Integrações ERP, webhooks e n8n | Pipeline de importação com normalização e jobs | Primeiro ERP/protocolo, direção do fluxo, autenticação, mapeamento e política de retentativa | Duplicação de compras, credenciais externas e falhas de sincronização |
| Notificações | Eventos e trilha de casos | Canais, gatilhos, preferências, destinatários e retenção | Entrega indevida e exposição de dados |
| Regras personalizadas e aprovação de ações corretivas | Motor de regras versionadas e ciclo de casos | Linguagem e limites das regras; estados, papéis e autoridade das aprovações | Alteração indevida da decisão de auditoria |

## Decisões que habilitaram a entrega do copiloto

1. Aprovação Owner/Admin para chats normais de Analyst quando o padrão da empresa for temporário: definida em `copilot-v2.md`.
2. Contrato, modelo de dados, experiência web, casos de erro e critérios de aceite: definidos em `copilot-v2.md` e `openapi.yaml`.
3. Entrega integrada: política, conversas, turnos, memória, citações, worker, interface e E2E. Os demais itens da Versão 2 permanecem fora do escopo.
4. A configuração e os dados do copiloto pertencem ao schema de negócios, após a separação da identidade. Toda leitura empresarial requer associação ativa e filtro por organização.

O copiloto pode reutilizar a infraestrutura local de IA e evidências, sem depender de um ERP ou serviço pago. A auditoria determinística e as decisões de casos continuam independentes da IA.
