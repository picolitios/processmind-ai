import AxeBuilder from '@axe-core/playwright'
import type { Page } from '@playwright/test'
import { expect } from '@playwright/test'

export async function assertAccessible(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  const issues = results.violations.flatMap(violation =>
    violation.nodes.map(node => `${violation.id}: ${node.target.join(', ')} ${node.failureSummary || ''}`),
  )
  expect(issues).toEqual([])
}
