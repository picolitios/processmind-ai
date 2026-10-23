import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ThemeProvider, ThemeToggle } from "./ThemeProvider";

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

test("alterna entre claro e escuro e restaura a escolha", () => {
  const view = render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
  expect(document.documentElement.dataset.theme).toBe("light");
  fireEvent.click(screen.getByRole("button", { name: "Ativar modo escuro" }));
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("processmind-theme")).toBe("dark");

  view.unmount();
  render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
  expect(document.documentElement.dataset.theme).toBe("dark");
  fireEvent.click(screen.getByRole("button", { name: "Ativar modo claro" }));
  expect(document.documentElement.dataset.theme).toBe("light");
});
