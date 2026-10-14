import { render, screen } from '@testing-library/react'
import { test, expect } from 'vitest'
import App from './App'

test('identifica a fase atual sem apresentar dados fictícios', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: 'ProcessMind AI' })).toBeTruthy()
  expect(screen.getByText(/fundação técnica/)).toBeTruthy()
})
