// Envia CSV/XLSX e acompanha o estado de cada importação da empresa.
import { useState } from "react";
import { Link, useOutletContext } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, orgPath } from "../../lib/api";
import type { ImportBatch, Page } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canWrite } from "../shell/Shell";

export function ImportsPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const [cursor, setCursor] = useState<string>();
  const [file, setFile] = useState<File | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const imports = useResource<Page<ImportBatch>>(
    ["imports", organizationId, cursor],
    orgPath(
      organizationId,
      `/imports${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
    ),
    Boolean(organizationId),
    5000,
  );
  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      const body = new FormData();
      body.set("file", file);
      if (reason.trim()) body.set("reimport_reason", reason.trim());
      await api(orgPath(organizationId, "/imports"), { method: "POST", body });
      setFile(null);
      setReason("");
      (event.target as HTMLFormElement).reset();
      await client.invalidateQueries({ queryKey: ["imports", organizationId] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha no envio");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DADOS DE ENTRADA</p>
          <h1>Importações</h1>
          <p className="muted">
            Envie compras em CSV ou XLSX, confira a prévia e acompanhe o
            processamento.
          </p>
        </div>
      </div>
      {canWrite(role) && (
        <section className="card upload-card">
          <div>
            <h2>Nova importação</h2>
            <p className="muted">
              O arquivo será validado antes do mapeamento.
            </p>
          </div>
          <form onSubmit={upload}>
            <label>
              Arquivo CSV ou XLSX
              <input
                type="file"
                accept=".csv,.xlsx"
                required
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <label>
              Motivo de reimportação{" "}
              <span className="hint">(somente para arquivo repetido)</span>
              <input
                maxLength={500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
            </label>
            <Feedback error={error} />
            <button className="button primary" disabled={busy || !file}>
              {busy ? "Enviando…" : "Enviar arquivo"}
            </button>
          </form>
        </section>
      )}
      <section className="card">
        <div className="card-heading">
          <h2>Histórico</h2>
          <span className="muted">Atualização automática</span>
        </div>
        <QueryState loading={imports.isLoading} error={imports.error} />
        {imports.data &&
          (imports.data.items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Arquivo</th>
                    <th>Status</th>
                    <th>Linhas</th>
                    <th>Erros</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {imports.data.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.filename}</strong>
                      </td>
                      <td>
                        <Status value={item.status} />
                      </td>
                      <td>{item.row_count}</td>
                      <td>{item.error_count}</td>
                      <td>
                        <Link
                          to={`/organizations/${organizationId}/imports/${item.id}`}
                        >
                          Abrir →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty">Nenhum arquivo importado ainda.</p>
          ))}
        {imports.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(imports.data!.next_cursor!)}
          >
            Próxima página
          </button>
        )}
      </section>
    </>
  );
}
export function Status({ value }: { value: string }) {
  const label: Record<string, string> = {
    preview: "Aguardando mapeamento",
    queued: "Na fila",
    running: "Processando",
    succeeded: "Concluído",
    failed: "Falhou",
    open: "Aberto",
    in_review: "Em revisão",
    resolved: "Resolvido",
    dismissed: "Descartado",
    unreviewed: "Não revisado",
  };
  return (
    <span className={`status status-${value}`}>{label[value] || value}</span>
  );
}
