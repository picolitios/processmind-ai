# Limite de autorização da organização v1

Status: aprovado como incremento reversível da Fase 2 da evolução arquitetural.
Complementa `membership-boundary-v1.md` e `audit-configuration-coordination-v1.md`.

## Escopo e contrato

- Em `BUSINESS_AUTH_MODE=identity`, o contrato privado de associação é a autoridade
  para sessão, organização ativa e papel. A API de negócios não consulta nem bloqueia
  `organizations` novamente após a resposta válida. O UUID da resposta deve coincidir
  com o solicitado e o usuário deve coincidir com a sessão introspectada.
- Ausência de sessão retorna 401; organização ou associação inativa/inexistente,
  404; papel insuficiente, 403; indisponibilidade ou resposta privada inválida, 503.
  Não consultar dados empresariais antes da autorização.
- O snapshot da auditoria usa a linha bloqueada de `audit_configurations` em modo
  `owned`. Aplicação de configuração e criação de auditoria serializam nessa linha;
  a versão e os valores do snapshot são sempre do mesmo estado confirmado.
- A identidade serializa reaplicações pelo comando pendente e não mantém bloqueio
  em `organizations` durante o HTTP privado. O bloqueio da organização para
  ativar um provisionamento ocorre após a confirmação da auditoria. Isso evita
  ciclo de espera entre o bloqueio da configuração e a FK da auditoria.
- O modo remoto exige `AUDIT_CONFIG_MODE=owned`. O modo local `database` preserva
  a leitura e o bloqueio legados de `organizations` para rollback, inclusive com
  `AUDIT_CONFIG_MODE=legacy`. A mudança de modo não migra nem apaga dados.
- Chamadas que antes pediam `for_update` à autorização continuam autorizando
  imediatamente antes da operação. No modo remoto, esse parâmetro não cria um
  bloqueio entre serviços. Revogações posteriores à resposta privada não cancelam
  uma transação já autorizada; a requisição seguinte consulta a identidade de novo.

## Aceite

1. No modo remoto, leitura, criação de auditoria e demais rotas empresariais não
   executam SELECT/LOCK em `organizations` pela autorização de associação.
2. Dois tenants, alteração de papel, revogação de sessão e falha da identidade
   mantêm os códigos e o isolamento existentes.
3. Alteração concorrente de configuração e criação de auditoria geram apenas o
   snapshot antigo completo ou o novo completo, nunca uma mistura.
4. A inicialização rejeita `BUSINESS_AUTH_MODE=identity` com configuração legada.
   O modo local continua utilizável após os gates de rollback já documentados.

## Fora do escopo

FKs entre domínios, referências históricas, permissões SQL e remoção da cópia
legada da configuração continuam sujeitos ao plano de cutover e à reconciliação.
