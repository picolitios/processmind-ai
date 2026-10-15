import { useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, json } from "../../lib/api";
import type { Organization } from "../../lib/api";
import { Feedback, QueryState } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { useAuth } from "../auth/AuthProvider";

export function OrganizationsPage() {
  const { orgs } = useOutletContext<ShellContext>();
  const navigate = useNavigate();
  const client = useQueryClient();
  const { refresh } = useAuth();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const org = await api<Organization>(
        "/organizations",
        json("POST", { name, slug }),
      );
      await refresh();
      await client.invalidateQueries({ queryKey: ["organizations"] });
      navigate(`/organizations/${org.id}/dashboard`);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Erro ao criar organização",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">WORKSPACES</p>
          <h1>Organizações</h1>
          <p className="muted">
            Selecione uma organização ou crie um espaço para sua equipe.
          </p>
        </div>
      </div>
      <QueryState loading={orgs.isLoading} error={orgs.error} />
      <div className="two-columns">
        <section className="card">
          <h2>Suas organizações</h2>
          {orgs.data?.length ? (
            <div className="list">
              {orgs.data.map((org) => (
                <Link
                  className="list-row"
                  key={org.id}
                  to={`/organizations/${org.id}/dashboard`}
                >
                  <span>
                    <strong>{org.name}</strong>
                    <small>{org.slug}</small>
                  </span>
                  <span>→</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="empty">Nenhuma organização disponível.</p>
          )}
        </section>
        <section className="card">
          <h2>Nova organização</h2>
          <p className="muted">Você será o proprietário deste espaço.</p>
          <form onSubmit={create}>
            <label>
              Nome
              <input
                required
                maxLength={160}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Identificador
              <input
                required
                maxLength={80}
                pattern="[a-z0-9]+(-[a-z0-9]+)*"
                value={slug}
                onChange={(e) =>
                  setSlug(
                    e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""),
                  )
                }
              />
            </label>
            <Feedback error={error} />
            <button className="button primary" disabled={busy}>
              {busy ? "Criando…" : "Criar organização"}
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
