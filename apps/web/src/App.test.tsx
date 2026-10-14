import { render, screen } from '@testing-library/react'
import { test, expect } from 'vitest'
import App from './App'

test('apresenta o estado atual sem dados fictícios', () => {
  render(<App />)
  expect(screen.getByRole('heading', { name: 'ProcessMind AI' })).toBeTruthy()
  expect(screen.getByText(/API de autenticação e organizações/)).toBeTruthy()
})
