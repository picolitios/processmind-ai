import { useState } from "react";
import { Link, useOutletContext } from "react-router";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import { orgPath, query } from "../../lib/api";
import type { Analytics } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";

export function DashboardPage() {
  const { organizationId } = useOutletContext<ShellContext>();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const data = useResource<Analytics>(
    ["analytics", organizationId, from, to],
    orgPath(organizationId, `/analytics/overview${query({ from, to })}`),
    Boolean(organizationId),
  );
  const metrics = data.data;
  const findings = metrics
    ? Object.values(metrics.findings_by_severity).reduce(
        (sum, value) => sum + value,
        0,
      )
    : 0;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">PAINEL DE CONTROLE</p>
          <h1>Visão geral</h1>
          <p className="muted">
            Acompanhe o panorama das suas auditorias e decisões.
          </p>
        </div>
        <div className="date-filters">
          <label>
            De
            <input
              aria-label="Data inicial"
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => setFrom(e.target.value)}
            />
          </label>
          <label>
            Até
            <input
              aria-label="Data final"
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => setTo(e.target.value)}
            />
          </label>
        </div>
      </div>
      <QueryState loading={data.isLoading} error={data.error} />
      {metrics && (
        <>
          <div className="metric-grid">
            <Metric label="Importações" value={metrics.imports} icon="⇧" />
            <Metric
              label="Registros analisados"
              value={metrics.analyzed_records}
              icon="▤"
            />
            <Metric label="Auditorias" value={metrics.audits} icon="◎" />
            <Metric label="Achados" value={findings} icon="◇" />
          </div>
          <div className="dashboard-grid">
            <section className="card chart-card">
              <div className="card-heading">
                <div>
                  <p className="eyebrow">MONITORAMENTO</p>
                  <h2>Evolução de achados</h2>
                </div>
                <Link to={`/organizations/${organizationId}/findings`}>
                  Ver alertas →
                </Link>
              </div>
              {metrics.trend.length ? (
                <div className="chart">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={metrics.trend}>
                      <defs>
                        <linearGradient
                          id="chartFill"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="var(--chart-line)"
                            stopOpacity={0.26}
                          />
                          <stop
                            offset="100%"
                            stopColor="var(--chart-line)"
                            stopOpacity={0}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(value) => String(value).slice(5)}
                        stroke="var(--muted)"
                      />
                      <YAxis allowDecimals={false} stroke="var(--muted)" />
                      <Tooltip />
                      <Area
                        type="monotone"
                        dataKey="count"
                        name="Achados"
                        stroke="var(--chart-line)"
                        strokeWidth={3}
                        fill="url(#chartFill)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="empty">Ainda não há achados no período.</p>
              )}
            </section>
            <section className="card case-summary">
              <p className="eyebrow">ACOMPANHAMENTO</p>
              <h2>Casos</h2>
              <div className="case-stat">
                <span>Pendentes</span>
                <strong>{metrics.pending_cases}</strong>
              </div>
              <div className="case-stat">
                <span>Resolvidos</span>
                <strong>{metrics.resolved_cases}</strong>
              </div>
              <div className="case-stat">
                <span>Descartados</span>
                <strong>{metrics.dismissed_cases}</strong>
              </div>
              <Link
                className="button secondary full"
                to={`/organizations/${organizationId}/cases`}
              >
                Abrir casos →
              </Link>
            </section>
          </div>
          <div className="dashboard-grid">
            <Ranking
              title="Fornecedores em compras auditadas"
              items={metrics.suppliers}
            />
            <Ranking
              title="Produtos em compras auditadas"
              items={metrics.products}
            />
          </div>
          {metrics.limitations.map((text) => (
            <p className="hint" key={text}>
              {text}
            </p>
          ))}
        </>
      )}
    </>
  );
}
function Metric({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: string;
}) {
  return (
    <div className="metric-card">
      <span className="metric-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value.toLocaleString("pt-BR")}</strong>
    </div>
  );
}
function Ranking({
  title,
  items,
}: {
  title: string;
  items: { name: string; count: number }[];
}) {
  return (
    <section className="card">
      <h2>{title}</h2>
      {items.length ? (
        items.map((item, index) => (
          <div className="rank-row" key={`${item.name}-${index}`}>
            <span className="rank-number">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span>{item.name}</span>
            <strong>{item.count}</strong>
          </div>
        ))
      ) : (
        <p className="empty">Sem dados no período.</p>
      )}
    </section>
  );
}
