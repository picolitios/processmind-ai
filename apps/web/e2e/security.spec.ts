import { expect, test } from '@playwright/test'

test('web aplica headers e API desabilita cache', async ({ request, page }) => {
  const web = await request.get('/')
  expect(web.ok()).toBeTruthy()
  const csp = web.headers()['content-security-policy']
  expect(csp).toContain("default-src 'self'")
  expect(csp).toContain("frame-ancestors 'none'")
  expect(web.headers()['x-content-type-options']).toBe('nosniff')
  expect(web.headers()['x-frame-options']).toBe('DENY')
  expect(web.headers()['referrer-policy']).toBe('strict-origin-when-cross-origin')
  expect(web.headers()['permissions-policy']).toContain('camera=()')

  const api = await request.get('/api/v1/health/ready')
  expect(api.ok()).toBeTruthy()
  expect(api.headers()['cache-control']).toBe('no-store')
  expect(api.headers()['x-processmind-service']).toBeUndefined()

  const identity = await request.get('/api/v1/auth/session')
  expect(identity.status()).toBe(401)
  expect(identity.headers()['x-processmind-service']).toBe('identity')

  const organizations = await request.get('/api/v1/organizations')
  expect(organizations.status()).toBe(401)
  expect(organizations.headers()['x-processmind-service']).toBe('identity')

  const internal = await request.post('/internal/v1/audit-config/apply', { data: {} })
  expect(internal.status()).toBe(404)

  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  page.on('console', message => {
    if (/content security policy|refused to (load|connect|execute|apply)/i.test(message.text())) errors.push(message.text())
  })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Bem-vindo de volta' })).toBeVisible()
  expect(errors).toEqual([])
})
