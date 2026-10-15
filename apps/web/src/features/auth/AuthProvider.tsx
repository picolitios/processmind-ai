import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, setCsrfToken } from "../../lib/api";
import type { Session } from "../../lib/api";

type AuthValue = {
  session: Session | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};
const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  async function refresh() {
    try {
      const next = await api<Session>("/auth/session");
      setSession(next);
      setCsrfToken(next.csrf_token);
    } catch {
      setSession(null);
      setCsrfToken("");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, []);
  async function login(email: string, password: string) {
    const next = await api<Session>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSession(next);
    setCsrfToken(next.csrf_token);
  }
  async function logout() {
    await api<void>("/auth/logout", { method: "POST" });
    setSession(null);
    setCsrfToken("");
  }
  return (
    <AuthContext.Provider value={{ session, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider ausente");
  return value;
}
