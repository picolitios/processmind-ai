import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

test("arquivo sintético gera os achados esperados", async ({ page }) => {
  test.setTimeout(180_000);
  const unique = Date.now().toString(36);
  await page.goto("/");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await page.getByLabel("Seu nome").fill("Usuário E2E");
  await page.getByLabel("E-mail").fill(`sample-${unique}@example.com`);
  await page.getByLabel("Senha").fill("senha-de-teste-12345");
  await page.getByRole("button", { name: "Criar conta", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: "Organizações", exact: true })).toBeVisible();

  await page.getByLabel("Nome").fill(`Amostra ${unique}`);
  await page.getByLabel("Identificador").fill(`sample-${unique}`);
  await page.getByRole("button", { name: "Criar organização" }).click();
  await page.getByRole("link", { name: "Importações" }).click();
  await page.getByLabel("Arquivo CSV ou XLSX").setInputFiles({
    name: "compras-teste-sinteticas.csv",
    mimeType: "text/csv",
    buffer: readFileSync(new URL("../../../examples/compras-teste-sinteticas.csv", import.meta.url)),
  });
  await page.getByRole("button", { name: "Enviar arquivo" }).click();
  await page.getByRole("link", { name: "Abrir →" }).click();

  // Mapeia todos os campos para que as regras de valor e entrega usem os dados do arquivo.
  const fields: Record<string, string> = {
    "ID da compra": "purchase_id",
    "ID do fornecedor": "supplier_id",
    "Data da compra": "purchase_date",
    "ID do produto": "product_id",
    Quantidade: "quantity",
    "Preço unitário": "unit_price",
    Moeda: "currency",
    "Valor total": "total_amount",
    "Nome do fornecedor": "supplier_name",
    "Nome do produto": "product_name",
    Unidade: "unit_of_measure",
    "Entrega prevista": "expected_delivery_date",
    "Entrega real": "actual_delivery_date",
  };
  for (const [label, column] of Object.entries(fields)) {
    await page.getByLabel(label, { exact: false }).selectOption(column);
  }
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await expect(page.getByText("Concluído").first()).toBeVisible({ timeout: 60_000 });

  await page.getByRole("link", { name: "Auditorias" }).click();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Executar auditoria" }).click();
  await page.getByRole("link", { name: "Abrir →" }).click();
  for (const rule of ["DUPLICATE", "TOTAL_MISMATCH", "LATE_DELIVERY"]) {
    await expect(page.getByRole("link", { name: new RegExp(rule) })).toBeVisible({ timeout: 60_000 });
  }
  await page.reload();
  await page.getByRole("button", { name: "Voltar à tela anterior" }).click();
  await expect(page.getByRole("heading", { name: "Auditorias", exact: true })).toBeVisible();
});
