# Guia de uso e demonstração

Comece pela [instalação local](installation.md). O exemplo [`compras-exemplo.csv`](../examples/compras-exemplo.csv) contém duas compras sintéticas com os mesmos atributos e IDs distintos; a regra `DUPLICATE` deve produzir um achado após a auditoria. Nenhum dado real é necessário.

Para um teste mais amplo, importe [`compras-teste-sinteticas.csv`](../examples/compras-teste-sinteticas.csv). Ele contém oito compras fictícias válidas. Associe as oito colunas obrigatórias e também `supplier_name`, `product_name`, `unit_of_measure`, `expected_delivery_date` e `actual_delivery_date` às colunas de mesmo nome. Após a importação concluída, a auditoria deve apontar ao menos `DUPLICATE` (compras 001/002), `TOTAL_MISMATCH` (003) e `LATE_DELIVERY` (004). O atraso depende do mapeamento das duas datas opcionais. Não reimporte o mesmo arquivo na mesma organização sem informar o motivo de reimportação.

O botão **Voltar à tela anterior** retorna à tela visitada antes da atual, inclusive quando ela foi aberta pelo menu ou por uma citação. Ao abrir um endereço diretamente ou recarregar a página, o botão leva à lista da seção; nas telas principais, leva à visão geral ou à lista de organizações.

## Roteiro de 10 minutos

1. Em <http://localhost:5173>, selecione **Criar conta** e cadastre um usuário de demonstração. Crie uma organização com nome e identificador únicos.
2. Abra **Importações**, escolha `examples/compras-exemplo.csv` e selecione **Enviar arquivo**. Abra a importação e confira a prévia.
3. No mapeamento, associe cada campo obrigatório à coluna de mesmo nome: `purchase_id`, `supplier_id`, `purchase_date`, `product_id`, `quantity`, `unit_price`, `currency` e `total_amount`. Confirme e aguarde **Concluído**. O worker processa a importação; erros de linha aparecem no detalhe.
4. Abra **Auditorias**, marque a importação concluída e selecione **Executar auditoria**. Aguarde o término e abra a execução. As regras são determinísticas e independem de IA.
5. Abra o achado `DUPLICATE` em **Alertas**. Consulte as evidências, selecione **Abrir caso**, atribua a si mesmo e adicione um comentário. Escolha **Resolvido**, escreva uma justificativa e salve a decisão.
6. Volte à **Visão geral**. Confira o total de uma auditoria, um achado e um caso resolvido. O painel é derivado dos dados persistidos da organização.

O detalhe do caso mostra atribuição, comentários e histórico. A opção de explicação por IA no achado é complementar e exige Ollama configurado; uma falha de IA não altera o resultado da auditoria.

## Copiloto conversacional (Versão 2)

Nos detalhes de um **achado** ou de uma **auditoria concluída**, Owner, Admin e Analyst podem abrir um chat pelo painel **Copiloto conversacional**. Escolha o tipo antes de selecionar **Novo chat**:

Em **Configurações → Agente e fontes**, Owner/Admin cadastram documentação
textual autorizada da empresa, habilitam as fontes e ativam o agente. A ferramenta
de análise de compras tem um controle separado. A fonte gerenciada é local ao
ambiente da empresa; ela ainda não representa conexão automática a ERP ou
repositório externo. Use somente conteúdo sintético na demonstração pública.

Quando ativado, o botão **Abrir agente** aparece no canto das telas da empresa.
Ele abre o chat sem sair da página; fechar e reabrir preserva o chat temporário
enquanto a página estiver carregada. Perguntas sobre processos consultam trechos
de fontes habilitadas e citam o documento. Pedidos de análise de compras usam
achados e evidências de auditorias concluídas se a ferramenta estiver habilitada.
O agente não executa ações, não consulta compras brutas ou casos e não acessa
outras empresas. Uma fonte alterada ou revogada deixa de ser citada como atual.
Viewer pode consultar fontes autorizadas, mas não inicia chats.

- **Normal:** perguntas e respostas ficam no histórico da organização. Abra um item em **Meus chats salvos** para continuar após recarregar a página. Outros usuários não leem sua transcrição, mas turnos de chats normais ativos da mesma organização podem compor a memória compartilhada do copiloto. Excluir o chat remove seus turnos dessa memória.
- **Temporário:** usa as evidências do alvo e as perguntas anteriores do próprio chat. Não usa outros chats nem entra na memória compartilhada. O painel não o restaura após recarregar; a transcrição transitória expira após uma hora sem atividade.

Em **Configurações → IA**, Owner/Admin podem escrever instruções da empresa (até 2.000 caracteres) para orientar o tom e o foco das próximas respostas do copiloto e da explicação dos alertas. Apagar o texto restaura o comportamento padrão. As instruções não alteram respostas já salvas, regras de auditoria, permissões nem a exigência de evidências e citações. Na mesma aba, Owner/Admin podem definir o modo temporário como padrão e ajustar de 0 a 20 os turnos de outros chats usados como memória. Com o temporário como padrão, um Analyst que criar chat normal aguarda aprovação. Owner/Admin decidem os pedidos nessa aba. O limite 0 desliga a memória entre chats; o histórico do chat atual continua disponível.

Após enviar uma pergunta, aguarde o processamento. A resposta mostra links para as evidências usadas, inclusive achados de outras auditorias da mesma organização quando a memória normal os recuperar. Confira cada evidência antes de decidir. Se Ollama estiver indisponível ou não houver evidências suficientes, o painel explica a limitação e a auditoria determinística continua funcionando.

## Conjuntos sintéticos maiores

Na raiz do repositório, com Python 3.12:

```powershell
python scripts/generate_synthetic.py --size 100 --seed 42 --output-dir synthetic-output
```

Os tamanhos aceitos são `100`, `1000`, `10000` e `50000`; a semente reproduz o mesmo CSV e gabarito JSON. Acrescente `--xlsx` para gerar planilha. `synthetic-output/` é ignorado pelo Git. Ao importar esses arquivos, mapeie colunas pelos mesmos nomes e consulte os erros de normalização antes de interpretar os achados. A [avaliação das regras](../specs/testing/audit-evaluation.md) explica os casos esperados; o [relatório de carga](../specs/testing/phase7-load-report.md) apresenta os tempos medidos.

## Capturas da demonstração

![Painel com auditoria e caso resolvido](screenshots/dashboard.png)

![Caso resolvido com justificativa, trilha e comentário](screenshots/case-resolved.png)

As capturas vieram do E2E em uma instalação com volumes novos. Nomes, IDs e datas pertencem a dados sintéticos do teste.
