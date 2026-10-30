import { expect, test } from "@playwright/test";

test("fonte pública do GitHub alimenta o agente com citação", async ({ page }) => {
  test.skip(process.env.PROCESSMIND_REQUIRE_GITHUB !== "1", "integração externa opt-in");
  test.setTimeout(300_000);
  const id = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await page.getByLabel("Seu nome").fill("Gestora GitHub E2E");
  await page.getByLabel("E-mail").fill(`github-${id}@example.com`);
  await page.getByLabel("Senha").fill("senha-de-teste-12345");
  await page.getByRole("button", { name: "Criar conta", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: "Organizações", exact: true })).toBeVisible();
  await page.getByLabel("Nome").fill(`GitHub E2E ${id}`);
  await page.getByLabel("Identificador").fill(`github-e2e-${id}`);
  await page.getByRole("button", { name: "Criar organização" }).click();
  await page.getByRole("link", { name: "Configurações" }).click();
  await page.getByRole("tab", { name: "Agente e fontes" }).click();

  const github = page.getByRole("heading", { name: "GitHub público" }).locator("..");
  await github.getByLabel("Proprietário do repositório").fill("picolitios");
  await github.getByLabel("Repositório", { exact: true }).fill("processmind-ai");
  await github.getByLabel("Caminho do arquivo").fill("README.md");
  await github.getByLabel("Título para o agente").fill("Manual do ProcessMind AI");
  await github.getByRole("button", { name: "Verificar e importar" }).click();
  await expect(page.getByText("Documento público verificado e importado.")).toBeVisible();
  await expect(page.getByText(/Origem: picolitios\/processmind-ai\/README.md/)).toBeVisible();
  await page.getByLabel("Agente flutuante ativo").check();
  await page.getByRole("button", { name: "Salvar capacidades" }).click();

  await page.getByRole("link", { name: "Visão geral" }).click();
  await page.getByRole("button", { name: "Abrir agente" }).click();
  const dialog = page.getByRole("dialog", { name: "Agente da empresa" });
  await dialog.getByRole("button", { name: "Novo chat" }).click();
  await dialog.getByLabel("Sua pergunta").fill("O que é o ProcessMind AI?");
  await dialog.getByRole("button", { name: "Enviar pergunta" }).click();
  const turn = dialog.locator(".copilot-turn").first();
  await expect(turn.getByText("Copiloto:")).toBeVisible({ timeout: 180_000 });
  await turn.getByRole("list", { name: "Fontes documentais" })
    .getByRole("link", { name: /Manual do ProcessMind AI/ }).click();
  await expect(page.getByRole("heading", { name: "Manual do ProcessMind AI" })).toBeVisible();
  await expect(page.getByText(/Cópia de picolitios\/processmind-ai\/README.md/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Ver versão atual no GitHub" })).toBeVisible();
});
