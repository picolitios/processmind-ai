# Configuração de auditoria: propriedade e transição v1

O corte posterior da gravação direta pela identidade está definido em
`audit-configuration-coordination-v1.md`.

`amount_limits`, `delay_window_days` e sua versão pertencem ao domínio de auditoria. A URL pública `PATCH /api/v1/organizations/{id}` e a resposta de organização permanecem compatíveis durante a transição.

## Incremento inicial

- A migração aditiva cria `audit_configurations` com uma linha por organização e copia os valores e a versão de `organizations`. A ausência de chave usa `{}` ou `90`; um `null` explícito preserva o valor anterior.
- Criar uma organização insere sua configuração na mesma transação. Alterar configurações atualiza a representação legada e a nova linha na mesma transação, com versão idêntica. Este acoplamento é transitório e ainda usa o banco compartilhado.
- Criar uma auditoria em modo `owned` lê e bloqueia a configuração de auditoria depois de validar associação e bloquear a organização; a versão e os valores no snapshot pertencem à mesma linha e transação. A ordem dos bloqueios é organização → configuração em ambos os fluxos. A ausência da configuração falha explicitamente.
- `AUDIT_CONFIG_MODE=legacy` reativa a leitura anterior sem perder dados. O modo `owned` deve ser ativado apenas após a migração e verificação da cópia. Não remover colunas ou FKs neste incremento.

## Aceite

1. Migração copia todas as organizações existentes, inclusive configurações não padrão, preservando versões; contagem e conteúdo são verificáveis.
2. Criar e alterar organização mantém as duas representações sincronizadas; o contrato HTTP permanece igual.
3. Atualização concorrente e criação de auditoria produzem apenas snapshot integral antigo ou novo, nunca mistura de versão e valores.
4. Falha ou linha ausente no modo `owned` não cai silenciosamente para os valores legados.
5. O modo `legacy` permite rollback de leitura; a migração não apaga dados nem concede isolamento de credenciais.
