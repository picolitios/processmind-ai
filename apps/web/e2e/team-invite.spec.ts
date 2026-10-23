import { expect, test } from "@playwright/test";

test("convite por e-mail só ativa membro após confirmação", async ({ browser, page, request }) => {
  const id = Date.now().toString(36);
  const ownerEmail = `owner-${id}@example.com`;
  const memberEmail = `member-${id}@example.com`;
  await page.goto("/");
  await page.getByRole("button", { name: "Criar conta" }).click();
  await page.getByLabel("Seu nome").fill("Ana Proprietária");
  await page.getByLabel("E-mail").fill(ownerEmail);
  await page.getByLabel("Senha").fill("senha-de-teste-12345");
  await page.getByRole("button", { name: "Criar conta", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: "Organizações", exact: true })).toBeVisible();
  await page.getByLabel("Nome").fill(`Empresa ${id}`);
  await page.getByLabel("Identificador").fill(`empresa-${id}`);
  await page.getByRole("button", { name: "Criar organização" }).click();
  await page.getByRole("link", { name: "Equipe" }).click();
  await page.getByLabel("E-mail").fill(memberEmail);
  await page.getByLabel("Cargo").selectOption("analyst");
  await page.getByRole("button", { name: "Enviar convite" }).click();
  await expect(page.getByText("Convite enviado.")).toBeVisible();
  await expect(page.getByText(memberEmail)).toBeVisible();
  const mailbox = process.env.E2E_MAILPIT_URL || "http://127.0.0.1:8025";
  let link = "";
  await expect.poll(async () => {
    const response = await request.get(`${mailbox}/view/latest.txt?query=${encodeURIComponent(`to:${memberEmail}`)}`);
    if (!response.ok()) return false;
    link = (await response.text()).match(/https?:\/\/[^\s]+\/invite#[\w-]+/)?.[0] || "";
    return Boolean(link);
  }).toBe(true);

  const invitedContext = await browser.newContext();
  const invited = await invitedContext.newPage();
  try {
    await invited.goto(link);
    await invited.getByRole("link", { name: "Entrar ou criar conta" }).click();
    await invited.getByRole("button", { name: "Criar conta" }).click();
    await invited.getByLabel("Seu nome").fill("Bruno Líder");
    await invited.getByLabel("E-mail").fill(memberEmail);
    await invited.getByLabel("Senha").fill("senha-de-teste-12345");
    await invited.getByRole("button", { name: "Criar conta", exact: true }).last().click();
    await expect(invited.getByRole("button", { name: "Confirmar convite" })).toBeVisible();
    await invited.getByRole("button", { name: "Confirmar convite" }).click();
    await expect(invited.getByRole("heading", { name: "Visão geral" })).toBeVisible();
    await invited.getByRole("link", { name: "Equipe" }).click();
    await expect(invited.getByText("Bruno Líder").first()).toBeVisible();
  } finally {
    await invitedContext.close();
  }
  await page.reload();
  await expect(page.getByText("Bruno Líder")).toBeVisible();
});
