# Casos e indicadores v1 — Fase 6

## Revisão e casos

- Cada achado admite no máximo um caso em todo seu histórico. O caso começa `open`; pode ir para `in_review`, `resolved` ou `dismissed`. De `in_review` pode ir para `resolved` ou `dismissed`. Estados finais não reabrem. Esta decisão foi confirmada pelo usuário.
- Abrir caso põe o achado em `in_review`. Enquanto há caso, alterações de revisão passam pelo caso. Encerrar caso exige justificativa de 1 a 1000 caracteres e atualiza o achado para o mesmo estado. Revisão direta sem caso usa as mesmas transições e exige justificativa para estado final.
- Um responsável precisa ser membro ativo da mesma organização. Mutação exige Owner/Admin/Analyst; Viewer só consulta. Comentários são append-only; o autor e a data são persistidos. Mudanças de estado, atribuição e fechamento geram `AuditEvent` com ator, data e metadados mínimos. Casos e comentários usam FKs compostas por organização.
- Listas usam cursor; detalhe do caso mostra comentários recentes e histórico. Comentários completos são paginados em rota própria.

## Indicadores

- `from`/`to` inclusivos usam datas próprias de cada entidade: criação da importação, data da compra, criação da auditoria, detecção do achado e abertura do caso. `to < from` é inválido. Todas as consultas filtram pelo tenant.
- `analyzed_records` conta compras válidas de importações incluídas em auditorias concluídas. Evolução agrupa achados por dia de detecção e retorna os 30 dias com achados mais recentes. Ranking de fornecedores usa compras auditadas e nome ou ID externo. O schema de compras não possui categoria; `categories` permanece vazio, e `products` fornece ranking por produto com limitação explícita. Nenhuma categoria é inferida.
- Contagens e rankings vêm do banco, sem dados fictícios. Listas longas no dashboard têm limite de 10 itens; páginas de entidades usam cursor.
