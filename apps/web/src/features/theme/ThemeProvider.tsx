import { createContext, useContext, useLayoutEffect, useState } from "react";

type Theme = "light" | "dark";
const storageKey = "processmind-theme";
const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void } | null>(null);

function savedTheme(): Theme {
  try {
    return localStorage.getItem(storageKey) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

// O tema é uma preferência deste navegador; nenhum dado da empresa é alterado.
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(savedTheme);
  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try {
      localStorage.setItem(storageKey, theme);
    } catch {
      // Navegação privada pode bloquear o armazenamento; o tema continua ativo na sessão.
    }
  }, [theme]);
  return (
    <ThemeContext.Provider value={{ theme, toggleTheme: () => setTheme((current) => current === "light" ? "dark" : "light") }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function ThemeToggle() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("ThemeToggle requer ThemeProvider");
  const dark = context.theme === "dark";
  return (
    <button className="theme-toggle" type="button" onClick={context.toggleTheme} aria-label={dark ? "Ativar modo claro" : "Ativar modo escuro"} aria-pressed={dark}>
      <span aria-hidden="true">{dark ? "☀" : "☾"}</span>
      <span>{dark ? "Modo claro" : "Modo escuro"}</span>
    </button>
  );
}
