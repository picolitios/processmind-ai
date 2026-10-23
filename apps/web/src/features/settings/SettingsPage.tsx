import { useEffect, useState } from "react";
import { useOutletContext } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, json, orgPath } from "../../lib/api";
import type { Organization } from "../../lib/api";
import { Feedback } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canAdmin } from "../shell/Shell";
import { CopilotSettings } from "../copilot/CopilotSettings";

export function SettingsPage() {
  const { organizationId, role, current } = useOutletContext<ShellContext>();
  const client = useQueryClient();
  const [delay, setDelay] = useState(90);
  const [currency, setCurrency] = useState("BRL");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<"audit" | "ai">("audit");
  useEffect(() => {
    if (current) {
      setDelay(current.settings.delay_window_days || 90);
      setAmount(current.settings.amount_limits?.[currency] || "");
    }
  }, [current, currency]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const limits = { ...current?.settings.amount_limits };
      if (amount) limits[currency] = amount;
      else delete limits[currency];
      await api<Organization>(
        orgPath(organizationId),
        json("PATCH", {
          delay_window_days: delay,
          amount_limits: limits,
        }),
      );
      await client.invalidateQueries({ queryKey: ["organizations"] });
      setSuccess("Configurações salvas.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao salvar");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ADMINISTRAÇÃO</p>
          <h1>Configurações</h1>
          <p className="muted">Parâmetros de auditoria e comportamento da IA.</p>
        </div>
      </div>
      <div className="item-tabs" role="tablist" aria-label="Configurações">
        <button type="button" role="tab" aria-selected={activeTab === "audit"}
          className={activeTab === "audit" ? "active" : ""}
          onClick={() => setActiveTab("audit")}>Auditoria</button>
        {canAdmin(role) && <button type="button" role="tab" aria-selected={activeTab === "ai"}
          className={activeTab === "ai" ? "active" : ""}
          onClick={() => setActiveTab("ai")}>IA</button>}
      </div>
      {activeTab === "audit" && <div>
        <section className="card">
          <h2>Parâmetros da organização</h2>
          <p className="muted">
            Versão atual: {current?.settings_version || "—"}
          </p>
          {canAdmin(role) ? (
            <form onSubmit={save}>
              <label>
                Janela de atraso (dias)
                <input
                  type="number"
                  min="1"
                  max="3650"
                  required
                  value={delay}
                  onChange={(e) => setDelay(Number(e.target.value))}
                />
              </label>
              <label>
                Moeda
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  <option value="BRL">BRL</option>
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                </select>
              </label>
              <label>
                Limite de valor
                <input
                  inputMode="decimal"
                  pattern="[0-9]+(\.[0-9]{1,2})?"
                  placeholder="Ex.: 10000.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </label>
              <button className="button primary" disabled={busy}>
                Salvar configurações
              </button>
            </form>
          ) : (
            <p className="empty">
              Somente administradores podem alterar configurações.
            </p>
          )}
        </section>
      </div>}
      {activeTab === "ai" && canAdmin(role) && <CopilotSettings organizationId={organizationId} />}
      {activeTab === "audit" && <Feedback error={error} success={success} />}
    </>
  );
}
