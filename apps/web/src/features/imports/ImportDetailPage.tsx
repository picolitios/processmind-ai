// Exibe a prévia, associa as colunas e confirma o processamento do arquivo.
import { useState } from "react";
import { useOutletContext, useParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, json, orgPath } from "../../lib/api";
import type { ImportBatch, Page } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canWrite } from "../shell/Shell";
import { Status } from "./ImportsPage";

type Preview = {
  headers: string[];
  rows: string[][];
  detected_encoding: string | null;
  delimiter: string | null;
};
type Row = {
  row_number: number;
  normalized: Record<string, unknown>;
  errors: { field: string; code: string }[];
};
const required = [
  "purchase_id",
  "supplier_id",
  "purchase_date",
  "product_id",
  "quantity",
  "unit_price",
  "currency",
  "total_amount",
];
const optional = [
  "supplier_name",
  "product_name",
  "unit_of_measure",
  "expected_delivery_date",
  "actual_delivery_date",
];
const labels: Record<string, string> = {
  purchase_id: "ID da compra",
  supplier_id: "ID do fornecedor",
  purchase_date: "Data da compra",
  product_id: "ID do produto",
  quantity: "Quantidade",
  unit_price: "Preço unitário",
  currency: "Moeda",
  total_amount: "Valor total",
  supplier_name: "Nome do fornecedor",
  product_name: "Nome do produto",
  unit_of_measure: "Unidade",
  expected_delivery_date: "Entrega prevista",
  actual_delivery_date: "Entrega real",
};
export function ImportDetailPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const { importId = "" } = useParams();
  const base = orgPath(organizationId, `/imports/${importId}`);
  const [rowCursor, setRowCursor] = useState("");
  const detail = useResource<ImportBatch>(
    ["import", importId],
    base,
    Boolean(importId),
    3000,
  );
  const preview = useResource<Preview>(
    ["preview", importId],
    `${base}/preview`,
    detail.data?.status === "preview",
  );
  const rows = useResource<Page<Row>>(
    ["rows", importId, rowCursor],
    `${base}/rows${rowCursor ? `?cursor=${encodeURIComponent(rowCursor)}` : ""}`,
    detail.data?.status === "succeeded",
  );
  const [columns, setColumns] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const client = useQueryClient();
  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const selected = Object.fromEntries(
        Object.entries(columns).filter(([, source]) => source),
      );
      await api(`${base}/confirm`, json("POST", { columns: selected }));
      await client.invalidateQueries({ queryKey: ["import", importId] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao confirmar");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">IMPORTAÇÃO</p>
          <h1>{detail.data?.filename || "Detalhe da importação"}</h1>
          <p className="muted">
            {detail.data && (
              <>
                <Status value={detail.data.status} /> · {detail.data.row_count}{" "}
                linhas · {detail.data.error_count} erros
              </>
            )}
          </p>
        </div>
      </div>
      <QueryState loading={detail.isLoading} error={detail.error} />
      {detail.data?.job?.error_code && (
        <Feedback
          error={`Falha no processamento: ${detail.data.job.error_code}`}
        />
      )}
      {detail.data?.status === "preview" && (
        <>
          <section className="card">
            <h2>Prévia do arquivo</h2>
            <QueryState loading={preview.isLoading} error={preview.error} />
            {preview.data && (
              <>
                <p className="hint">
                  {preview.data.rows.length} linhas de exemplo ·{" "}
                  {preview.data.detected_encoding || "XLSX"}
                </p>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {preview.data.headers.map((header) => (
                          <th key={header}>{header}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.data.rows.map((row, index) => (
                        <tr key={index}>
                          {row.map((cell, cellIndex) => (
                            <td key={cellIndex}>{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
          {canWrite(role) && preview.data && (
            <section className="card">
              <h2>Mapeamento de colunas</h2>
              <p className="muted">
                Associe cada campo à coluna correspondente do arquivo. Os campos
                marcados são obrigatórios.
              </p>
              <form onSubmit={confirm} className="mapping-grid">
                {[...required, ...optional].map((field) => (
                  <label key={field}>
                    {labels[field]} {required.includes(field) && "*"}
                    <select
                      required={required.includes(field)}
                      value={columns[field] || ""}
                      onChange={(e) =>
                        setColumns({ ...columns, [field]: e.target.value })
                      }
                    >
                      <option value="">Selecione uma coluna</option>
                      {preview.data.headers.map((header) => (
                        <option key={header} value={header}>
                          {header}
                        </option>
                      ))}
                    </select>
                  </label>
                ))}
                <div>
                  <Feedback error={error} />
                  <button className="button primary" disabled={busy}>
                    {busy ? "Confirmando…" : "Confirmar importação"}
                  </button>
                </div>
              </form>
            </section>
          )}
        </>
      )}
      {detail.data?.status === "succeeded" && (
        <section className="card">
          <h2>Linhas processadas</h2>
          <QueryState loading={rows.isLoading} error={rows.error} />
          {rows.data?.items.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Linha</th>
                    <th>Resultado</th>
                    <th>Dados normalizados</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.data.items.map((row) => (
                    <tr key={row.row_number}>
                      <td>{row.row_number}</td>
                      <td>
                        {row.errors.length
                          ? row.errors
                              .map((item) => `${item.field}: ${item.code}`)
                              .join(", ")
                          : "Válida"}
                      </td>
                      <td>
                        <code>{JSON.stringify(row.normalized)}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty">Nenhuma linha disponível.</p>
          )}
          {rows.data?.next_cursor && (
            <button
              className="button secondary"
              onClick={() => setRowCursor(rows.data!.next_cursor!)}
            >
              Próxima página
            </button>
          )}
        </section>
      )}
    </>
  );
}
