import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { assertAccessible } from "./assertAccessible";

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
  await assertAccessible(page);

  await page.getByLabel("Nome").fill(`Teste E2E ${unique}`);
  await page.getByLabel("Identificador").fill(`e2e-${unique}`);
  await page.getByRole("button", { name: "Criar organização" }).click();
  await expect(
    page.getByRole("heading", { name: "Visão geral" }),
  ).toBeVisible();
  await assertAccessible(page);

  await page.getByRole("link", { name: "Importações" }).click();
  await assertAccessible(page);
  await page
    .getByLabel("Arquivo CSV ou XLSX")
    .setInputFiles({
      name: "compras-exemplo.csv",
      mimeType: "text/csv",
      buffer: readFileSync(
        new URL("../../../examples/compras-exemplo.csv", import.meta.url),
      ),
    });
  await page.getByRole("button", { name: "Enviar arquivo" }).click();
  await expect(page.getByRole("link", { name: "Abrir →" })).toBeVisible();
  await page.getByRole("link", { name: "Abrir →" }).click();
  await expect(
    page.getByRole("heading", { name: "Mapeamento de colunas" }),
  ).toBeVisible();
  await assertAccessible(page);
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
  await expect(page.getByRole("checkbox")).toBeVisible();
  await assertAccessible(page);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Executar auditoria" }).click();
  await expect(page.getByRole("link", { name: "Abrir →" })).toBeVisible();
  await page.getByRole("link", { name: "Abrir →" }).click();
  await expect(page.getByRole("link", { name: /DUPLICATE/ })).toBeVisible({
    timeout: 60_000,
  });
  await assertAccessible(page);
  const auditUrl = page.url();
  const auditCopilot = page.getByRole("region", { name: "Copiloto conversacional" });
  await auditCopilot.getByRole("button", { name: "Novo chat" }).click();
  await expect(auditCopilot.getByRole("heading", { name: "Chat salvo" })).toBeVisible();
  await auditCopilot.getByLabel("Sua pergunta").fill("Quais evidências devo conferir?");
  await auditCopilot.getByRole("button", { name: "Enviar pergunta" }).click();
  await expect(auditCopilot.getByText("Quais evidências devo conferir?")).toBeVisible();
  const firstTurn = auditCopilot.locator(".copilot-turn").first();
  await expect(firstTurn.getByText("Resposta em processamento…")).toHaveCount(0, {
    timeout: 60_000,
  });
  await expect(firstTurn.locator("p").filter({
    hasText: /Copiloto:|Ollama indisponível|Dados insuficientes|Resposta da IA inválida/,
  })).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(auditUrl);
  await auditCopilot.getByRole("button", { name: /Ativo/ }).click();
  await expect(auditCopilot.getByText("Quais evidências devo conferir?")).toBeVisible();

  await page.getByRole("link", { name: "Alertas" }).click();
  await expect(page.getByRole("heading", { name: "Achados" })).toBeVisible();
  await assertAccessible(page);
  await page.getByRole("link", { name: /DUPLICATE/ }).click();
  await assertAccessible(page);
  const findingCopilot = page.getByRole("region", { name: "Copiloto conversacional" });
  await findingCopilot.getByLabel("Tipo de chat").selectOption("temporary");
  await findingCopilot.getByRole("button", { name: "Novo chat" }).click();
  await expect(findingCopilot.getByRole("heading", { name: "Chat temporário" })).toBeVisible();
  await findingCopilot.getByLabel("Sua pergunta").fill("O que verificar neste achado?");
  await findingCopilot.getByRole("button", { name: "Enviar pergunta" }).click();
  await expect(findingCopilot.getByText("O que verificar neste achado?")).toBeVisible();
  await page.reload();
  await expect(findingCopilot.getByText("Nenhum chat salvo para este alvo.")).toBeVisible();
  await expect(findingCopilot.getByRole("heading", { name: "Chat temporário" })).toHaveCount(0);
  await page.getByRole("button", { name: "Abrir caso" }).click();
  await expect(page.getByRole("heading", { name: /Caso/ })).toBeVisible();
  await assertAccessible(page);
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
  if (process.env.PROCESSMIND_SCREENSHOT_DIR) {
    await page.setViewportSize({ width: 1280, height: 1080 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({
      path: join(process.env.PROCESSMIND_SCREENSHOT_DIR, "case-resolved.png"),
    });
  }
  await page.getByRole("link", { name: "Casos", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Casos" })).toBeVisible();
  await assertAccessible(page);
  await page.getByRole("link", { name: "Visão geral" }).click();
  await expect(
    page.locator(".case-stat").filter({ hasText: "Resolvidos" }).getByText("1"),
  ).toBeVisible();
  if (process.env.PROCESSMIND_SCREENSHOT_DIR) {
    await page.screenshot({
      path: join(process.env.PROCESSMIND_SCREENSHOT_DIR, "dashboard.png"),
      fullPage: true,
    });
  }
  await page.getByRole("link", { name: "Configurações" }).click();
  await expect(page.getByRole("heading", { name: "Configurações" })).toBeVisible();
  await assertAccessible(page);
  await page.getByLabel("Iniciar chats no modo temporário por padrão").check();
  await page.getByRole("button", { name: "Salvar política do copiloto" }).click();
  await expect(page.getByText("Política do copiloto salva.")).toBeVisible();
});
