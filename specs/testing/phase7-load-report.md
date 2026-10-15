# Carga da Fase 7

## Método

Em 15/10/2026, no host Windows do desenvolvimento, PostgreSQL 16 via Docker e API/worker Python 3.12 locais, executei `scripts/benchmark_pipeline.py` com semente 42 em bancos PostgreSQL dedicados `processmind_bench_*` recém-migrados. O script usa HTTP via `TestClient` para cadastro, organização, upload, prévia/mapeamento, criação de auditoria e paginação; `run_once()` processa os jobs. Tempo de upload e dos dois jobs vem de `perf_counter`. Memória é o maior RSS observado do processo Python em amostras de 100 ms; inclui o processo de teste e não representa memória total do PostgreSQL ou contêiner.

Esta rodada de carga é sequencial e usa um único host. Arquivos sintéticos ficaram em `synthetic-output/`, ignorado pelo Git. Não foram usados dados reais. O teste separado `test_concurrent_import_jobs_remain_isolated` executa dois workers simultâneos em organizações distintas e verifica conclusão, uma compra por importação e resposta 404 entre organizações. A navegação E2E com Axe percorre as onze telas do fluxo.

| Linhas | Ingestão antes | Ingestão após | Auditoria após | Pico RSS após, ingestão | Pico RSS após, auditoria | Achados |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 0,705 s | 0,178 s | 0,074 s | 95,2 MiB | 95,4 MiB | 6 |
| 1.000 | 6,356 s | 0,686 s | 0,363 s | 104,5 MiB | 104,5 MiB | 78 |
| 10.000 | 63,548 s | 6,107 s | 6,173 s | 106,3 MiB | 125,8 MiB | 780 |
| 50.000 | 323,919 s | 29,207 s | 35,991 s | 119,1 MiB | 234,3 MiB | 3.899 |

Antes e depois usaram o mesmo gerador e semente, bancos novos e o mesmo host. Em 50.000 linhas, a ingestão ficou aproximadamente 11 vezes mais rápida. A mudança removeu `flush` por linha e consultas repetidas de fornecedor; `ImportRow` recebe UUID antes da gravação, as gravações são descarregadas em lotes de 500 e fornecedores são reutilizados dentro do job. O número de linhas, achados e a paginação ficaram consistentes nas duas execuções. Os 18 testes Python, incluindo ingestão concorrente, isolamento e auditoria, passaram depois da alteração.

## Limitações da medição

- O pico RSS não inclui PostgreSQL nem outros contêineres. Não foi medido o pico total do Compose.
- Os tempos dependem do host de desenvolvimento e não definem SLO de produção. Antes de fixar um SLO, repetir a medição em ambiente representativo.
- A concorrência foi verificada com duas importações pequenas; carga concorrente de 50.000 linhas não foi medida.
