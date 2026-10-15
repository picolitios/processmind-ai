import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { test, expect, vi } from "vitest";
import App from "./App";

test("mostra o acesso quando não há sessão", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ message: "Não autenticado" }),
      }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(
    await screen.findByRole("heading", { name: "Bem-vindo de volta" }),
  ).toBeTruthy();
  expect(screen.getByRole("button", { name: "Entrar" })).toBeTruthy();
  vi.unstubAllGlobals();
});
