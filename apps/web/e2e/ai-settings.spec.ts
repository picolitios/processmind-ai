import { expect, test } from "@playwright/test";

test("proprietário salva instruções da IA na empresa", async ({ page }) => {
  const id = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await page.getByLabel("Seu nome").fill("Gestora E2E");
  await page.getByLabel("E-mail").fill(`ia-${id}@example.com`);
  await page.getByLabel("Senha").fill("senha-de-teste-12345");
  await page.getByRole("button", { name: "Criar conta", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: "Organizações", exact: true })).toBeVisible();
  await page.getByLabel("Nome").fill(`Empresa IA ${id}`);
  await page.getByLabel("Identificador").fill(`empresa-ia-${id}`);
  await page.getByRole("button", { name: "Criar organização" }).click();

  await page.getByRole("link", { name: "Configurações" }).click();
  await page.getByRole("tab", { name: "IA" }).click();
  const instructions = page.getByLabel("Instruções da empresa para a IA");
  await instructions.fill("Explique o resultado em até três frases.");
  await page.getByRole("button", { name: "Salvar política do copiloto" }).click();
  await expect(page.getByText("Configurações da IA salvas.", { exact: false })).toBeVisible();
  await page.reload();
  await page.getByRole("tab", { name: "IA" }).click();
  await expect(instructions).toHaveValue("Explique o resultado em até três frases.");
});
