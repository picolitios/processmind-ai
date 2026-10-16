# Coordenação da configuração de auditoria v1

Este incremento sucede `audit-configuration-ownership-v1.md`. Aquele documento
descreve a gravação dupla atômica de preparação; este remove a escrita direta da
identidade em `audit_configurations` quando `AUDIT_CONFIG_WRITE_MODE=coordinated`.
O modo coordenado exige `AUDIT_CONFIG_MODE=owned` para o snapshot da auditoria.
O modo `database` permanece temporariamente para rollback no banco compartilhado.
As URLs, formatos e códigos de sucesso públicos da organização permanecem iguais.

## Propriedade e contrato privado

- A identidade é proprietária de organização, associação, sessão e de um comando
  durável de provisionamento/alteração por `(organization_id, settings_version)`.
  O comando guarda apenas os valores de configuração necessários à auditoria.
- O domínio de auditoria expõe `POST /internal/v1/audit-config/apply`, inacessível
  pelo nginx. A chamada é assinada com HMAC sobre horário e corpo canônico, expira
  em 30 segundos e usa a chave interna já configurada. O endpoint não aceita
  sessão do cliente como autoridade e não aparece no OpenAPI público.
- A auditoria aplica uma versão somente se a versão atual for a anterior. Repetir
  o mesmo comando e conteúdo retorna sucesso sem nova alteração. Versão ou
  conteúdo conflitante não são sobrescritos. A configuração é gravada em uma
  transação do domínio de auditoria; criação de auditoria lê apenas a linha
  confirmada, bloqueada para preservar o snapshot integral.

## Operação pública

- `POST /organizations`: a identidade persiste organização em estado
  `provisioning`, associação owner e comando inicial na mesma transação. Após a
  confirmação da auditoria, ativa a organização e retorna `201` com a resposta
  existente. Falha/timeout retorna `503`; a organização permanece invisível às
  operações empresariais até a reconciliação. O slug fica reservado.
  Repetir o mesmo slug e nome pelo mesmo owner conclui ou consulta o mesmo
  provisionamento e retorna a mesma organização; outro solicitante recebe `409`.
- `PATCH /organizations/{id}`: validar sessão, CSRF e papel; serializar por linha
  da organização. Persistir o comando e a cópia legada da resposta na mesma
  transação. Aplicar o comando na auditoria e retornar `200` apenas depois da
  confirmação. Se houver falha, retornar `503` e manter o comando pendente.
- Leituras de organização que incluam configurações retornam `503` se houver
  comando pendente para o respectivo tenant, em vez de expor uma versão ainda não
  confirmada. Listagens continuam filtradas por associação e organização ativa.
- Um pedido subsequente de alteração pode concluir primeiro o comando pendente
  com a mesma rotina idempotente; não cria uma versão nova enquanto a anterior
  estiver sem confirmação. Repetir uma alteração já refletida nos valores
  confirmados retorna a versão atual sem criar outro comando.
- O modo `database` conserva a transação anterior para rollback local. Antes de
  voltar a ele, drenar comandos e conferir versão e valores das duas cópias.

## Reconciliação e falhas

- Um worker da identidade tenta novamente comandos pendentes com espera entre
  tentativas. A confirmação após timeout é segura porque o apply é idempotente.
  Falha permanente de versão/conteúdo fica visível para intervenção; não há
  correção silenciosa. Nenhum segredo ou valor de configuração é logado.
- Um comando confirmado pela auditoria, mas não marcado como concluído pela
  identidade, é reaplicável. Criar uma organização durante indisponibilidade
  nunca responde `201` antes de seu provisionamento.
- A migração é aditiva e não apaga configurações legadas. Antes de ativar o modo
  coordenado, comparar contagens, versões e valores das duas representações.
  Não retirar FKs entre domínios nem credenciais compartilhadas neste incremento.

## Aceite

1. Criação e alteração retornam `201`/`200` com o formato atual somente após
   aplicar exatamente a versão solicitada na auditoria.
2. Repetição após timeout não duplica versões ou eventos; payload conflitante
   não altera a configuração confirmada.
3. Indisponibilidade deixa comando recuperável, responde `503` e não expõe
   configuração pendente como confirmada.
4. Alteração concorrente e criação de auditoria produzem apenas snapshots
   completos antigos ou novos; organização inativa/provisioning não cria auditoria.
5. Reconciliação automática e inspeção operacional mostram pendências sem
   eliminar dados; modo anterior continua disponível após drenagem verificada.
