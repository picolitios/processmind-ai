# Stack e dependências

| Camada | Tecnologia | Justificativa |
| --- | --- | --- |
| Web | React, TypeScript strict, Vite | SPA tipada e build local simples |
| UI | Tailwind CSS, React Router, TanStack Query, React Hook Form, Zod, Recharts | Estilos, navegação, estado de servidor, formulário, validação e gráficos conforme o prompt |
| API | Python 3.12, FastAPI, Pydantic, SQLAlchemy 2 | Contratos tipados, validação e persistência |
| Banco | PostgreSQL, Alembic | Transações, constraints, índices e migrações versionadas |
| Análise | pandas, NumPy, scikit-learn | Pipeline de dados; usar inicialmente métodos estatísticos simples |
| IA | Ollama local | Sem cobrança por API; falha isolada da auditoria |
| Qualidade | Pytest, Ruff, Mypy, Vitest, Testing Library, Playwright | Verificação por camada |
| Infra | Docker Compose e GitHub Actions | Execução local e CI em limites gratuitos |

Dependências adicionais devem ser justificadas em cada fase. O driver PostgreSQL, parser XLSX, hash de senha e suporte a multipart são dependências técnicas esperadas nas fases em que forem usados. Nenhuma versão de biblioteca é prometida aqui antes de ser instalada e validada.
