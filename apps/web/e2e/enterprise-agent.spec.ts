import { expect, test } from "@playwright/test";

test("empresa habilita fonte e abre agente flutuante sem sair da tela", async ({ page }) => {
  const id = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await page.getByLabel("Seu nome").fill("Gestora E2E");
  await page.getByLabel("E-mail").fill(`agente-${id}@example.com`);
  await page.getByLabel("Senha").fill("senha-de-teste-12345");
  await page.getByRole("button", { name: "Criar conta", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: "Organizações", exact: true })).toBeVisible();
  await page.getByLabel("Nome").fill(`Empresa Agente ${id}`);
  await page.getByLabel("Identificador").fill(`empresa-agente-${id}`);
  await page.getByRole("button", { name: "Criar organização" }).click();
  await page.getByRole("link", { name: "Configurações" }).click();
  await expect(page.getByRole("button", { name: "Abrir agente" })).toHaveCount(0);

  await page.getByRole("tab", { name: "Agente e fontes" }).click();
  await page.getByLabel("Título").fill("Aprovação de compras");
  await page.getByLabel("Procedimento ou documentação").fill(
    "O líder analisa o pedido de compra e registra a aprovação antes da emissão.",
  );
  await page.getByLabel("Fonte habilitada").check();
  await page.getByRole("button", { name: "Salvar fonte" }).click();
  await expect(page.getByText("Fonte criada.")).toBeVisible();
  await page.getByLabel("Agente flutuante ativo").check();
  await page.getByRole("button", { name: "Salvar capacidades" }).click();
  await expect(page.getByRole("button", { name: "Abrir agente" })).toBeVisible();

  await page.getByRole("link", { name: "Visão geral" }).click();
  const dashboard = page.getByRole("heading", { name: "Visão geral" });
  await expect(dashboard).toBeVisible();
  await page.getByRole("button", { name: "Abrir agente" }).click();
  const dialog = page.getByRole("dialog", { name: "Agente da empresa" });
  await expect(dialog).toBeVisible();
  await expect(dashboard).toBeVisible();
  await dialog.getByRole("button", { name: "Novo chat" }).click();
  await dialog.getByLabel("Sua pergunta").fill("Como funciona a aprovação de compras?");
  await dialog.getByRole("button", { name: "Enviar pergunta" }).click();
  await expect(dialog.getByText("Como funciona a aprovação de compras?", { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Fechar agente" }).click();
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Abrir agente" }).click();
  await expect(dialog.getByText("Como funciona a aprovação de compras?", { exact: true })).toBeVisible();
});
