# Equipe, convites e atividade dos alertas v1

## Decisões

- Manter os papéis persistidos `owner`, `admin`, `analyst`, `viewer` e o RBAC existente. Na interface, `analyst` aparece como **Líder** e `viewer` como **Funcionário**. A configuração granular de permissões fica para uma entrega futura; esta mudança não amplia privilégios.
- O usuário registra um nome de exibição. Contas antigas podem completá-lo no próprio perfil; até lá, o e-mail identifica o autor. O nome exibido é resolvido na identidade, inclusive para membros inativos, e não substitui o ID imutável nos eventos.
- O proprietário convida por e-mail. Convite pendente não cria associação ativa. A pessoa confirma o endereço ao abrir o link recebido, autenticando-se com a mesma conta ou cadastrando-se, e aceita a associação. O token é aleatório, tem validade limitada, é armazenado apenas como hash e nunca aparece na API de administração nem em logs.
- O envio usa SMTP configurável. Na demo local, Mailpit captura a mensagem em uma interface ligada somente ao loopback. Sem SMTP configurado, a API não declara um convite enviado. A implantação pública só pode entregar e-mails reais após configuração explícita de um SMTP externo; Mailpit não envia para destinatários reais.

## Alertas e atividade

- A lista de alertas identifica o produto analisado, fornecedor para atraso recorrente, ou linha de importação rejeitada. Abas agrupam os alertas por essa identificação na página carregada; filtros e paginação permanecem disponíveis.
- A justificativa da revisão direta já gravada em `business_audit_events` é exibida numa aba **Atividade** do achado, com estado anterior, novo estado, data e nome do autor. Inclui revisões existentes, sem alterar os eventos originais.
- Comentários e decisões de caso permanecem associados ao único caso do achado. A atividade do achado dá acesso ao caso; no detalhe do caso, comentários, fechamento e trilha mostram autor e justificativa. Registros permanecem consultáveis após conclusão ou descarte.
- Consultas de atividade exigem associação ativa à organização e filtram pelo `organization_id`. IDs de ator são resolvidos por contrato privado da identidade, sem conceder à API de negócios leitura do schema da identidade.

## Convites e segurança

- Apenas `owner` cria ou cancela convites e altera papéis. `owner`/`admin` consultam a equipe. A pessoa convidada só aceita o convite para o e-mail autenticado; token expirado, usado, revogado ou de outra conta não cria associação.
- A aceitação é idempotente para a associação já criada pelo mesmo convite. Conflitos com associação existente têm resposta explícita. A associação só passa a ativa depois da confirmação.
- A API limita a emissão de convites por organização e e-mail. A aceitação exige sessão e CSRF e usa token aleatório de 256 bits; não existe consulta anônima de validade do token. O navegador remove o fragmento da URL antes da chamada à API.
- Eventos de convite, aceitação e alteração de nome preservam ator e horário. O envio de e-mail não registra token nem conteúdo em logs.

## Aceite

1. Uma revisão direta exibe sua justificativa e autor após recarga, inclusive quando concluída ou descartada.
2. Alertas de produtos diferentes aparecem em grupos identificáveis; a navegação para cada detalhe preserva o vínculo correto.
3. O proprietário convida por e-mail sem ativar acesso prematuramente; a pessoa entra com o mesmo endereço e confirma o convite antes de ver a organização.
4. Comentários, revisões, descarte e fechamento mostram nome (ou e-mail de conta antiga) e data; revogar um membro não apaga a autoria histórica.
5. Testes verificam isolamento por organização, token inválido/expirado, permissões, fluxo de convite e histórico de revisão; lint, tipos, build e E2E relevantes passam.
