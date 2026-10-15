import { expect, test } from "@playwright/test";

test("cadastro até resolução de um caso", async ({ page }) => {
  const unique = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await page.getByLabel("E-mail").fill(`e2e-${unique}@example.com`);
  await page.getByLabel("Senha").fill("senha-de-teste-12345");
  await page
    .getByRole("button", { name: "Criar conta", exact: true })
    .last()
    .click();
  await expect(
    page.getByRole("heading", { name: "Organizações", exact: true }),
  ).toBeVisible();

  await page.getByLabel("Nome").fill(`Teste E2E ${unique}`);
  await page.getByLabel("Identificador").fill(`e2e-${unique}`);
  await page.getByRole("button", { name: "Criar organização" }).click();
  await expect(
    page.getByRole("heading", { name: "Visão geral" }),
  ).toBeVisible();

  await page.getByRole("link", { name: "Importações" }).click();
  const csv = [
    "purchase_id,supplier_id,purchase_date,product_id,quantity,unit_price,currency,total_amount",
    "P-1,S-1,2025-01-01,SKU-1,2,10,BRL,20",
    "P-2,S-1,2025-01-01,SKU-1,2,10,BRL,20",
  ].join("\n");
  await page
    .getByLabel("Arquivo CSV ou XLSX")
    .setInputFiles({
      name: "compras.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(csv),
    });
  await page.getByRole("button", { name: "Enviar arquivo" }).click();
  await expect(page.getByRole("link", { name: "Abrir →" })).toBeVisible();
  await page.getByRole("link", { name: "Abrir →" }).click();
  await expect(
    page.getByRole("heading", { name: "Mapeamento de colunas" }),
  ).toBeVisible();
  for (const field of [
    "ID da compra",
    "ID do fornecedor",
    "Data da compra",
    "ID do produto",
    "Quantidade",
    "Preço unitário",
    "Moeda",
    "Valor total",
  ]) {
    const source: Record<string, string> = {
      "ID da compra": "purchase_id",
      "ID do fornecedor": "supplier_id",
      "Data da compra": "purchase_date",
      "ID do produto": "product_id",
      Quantidade: "quantity",
      "Preço unitário": "unit_price",
      Moeda: "currency",
      "Valor total": "total_amount",
    };
    await page.getByLabel(`${field} *`).selectOption(source[field]);
  }
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(page.getByText("Concluído").first()).toBeVisible({
    timeout: 60_000,
  });

  await page.getByRole("link", { name: "Auditorias" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Executar auditoria" }).click();
  await expect(page.getByRole("link", { name: "Abrir →" })).toBeVisible();
  await page.getByRole("link", { name: "Abrir →" }).click();
  await expect(page.getByRole("link", { name: /DUPLICATE/ })).toBeVisible({
    timeout: 60_000,
  });
  await page.getByRole("link", { name: /DUPLICATE/ }).click();
  await page.getByRole("button", { name: "Abrir caso" }).click();
  await expect(page.getByRole("heading", { name: /Caso/ })).toBeVisible();
  await page
    .getByLabel("Atribuir responsável")
    .selectOption({ label: `Eu (e2e-${unique}@example.com)` });
  await page.getByRole("button", { name: "Atribuir", exact: true }).click();
  await expect(page.getByText("Responsável atualizado.")).toBeVisible();
  await page
    .getByLabel("Novo comentário")
    .fill("Conferência iniciada pelo E2E.");
  await page.getByRole("button", { name: "Adicionar comentário" }).click();
  await expect(page.getByText("Conferência iniciada pelo E2E.")).toBeVisible();
  await page.getByLabel("Novo status").selectOption("resolved");
  await page
    .getByLabel("Justificativa")
    .fill("Compra verificada e tratada pelo responsável.");
  await page.getByRole("button", { name: "Salvar decisão" }).click();
  await expect(page.getByText("Resolvido").first()).toBeVisible();
  await page.getByRole("link", { name: "Visão geral" }).click();
  await expect(
    page.locator(".case-stat").filter({ hasText: "Resolvidos" }).getByText("1"),
  ).toBeVisible();
});
