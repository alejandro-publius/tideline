import { useSyncExternalStore } from 'react'

/**
 * Chart colors must be concrete values (SVG presentation attributes can't
 * resolve CSS variables), so the palette lives here and index.css mirrors it.
 * Validated for CVD separation and surface contrast in both modes.
 */
export interface ChartTheme {
  observed: string
  predicted: string
  /** diverging pair for the surge residual: above / below prediction */
  surgeAbove: string
  surgeBelow: string
  grid: string
  baseline: string
  muted: string
  surface: string
}

export const LIGHT: ChartTheme = {
  observed: '#2a78d6',
  predicted: '#1baf7a',
  surgeAbove: '#e34948',
  surgeBelow: '#2a78d6',
  grid: '#e1e0d9',
  baseline: '#c3c2b7',
  muted: '#898781',
  surface: '#fcfcfb',
}

export const DARK: ChartTheme = {
  observed: '#3987e5',
  predicted: '#199e70',
  surgeAbove: '#e66767',
  surgeBelow: '#3987e5',
  grid: '#2c2c2a',
  baseline: '#383835',
  muted: '#898781',
  surface: '#1a1a19',
}

const DARK_QUERY = '(prefers-color-scheme: dark)'

export function usePrefersDark(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(DARK_QUERY)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    () => window.matchMedia(DARK_QUERY).matches,
  )
}

export const useChartTheme = (): ChartTheme => (usePrefersDark() ? DARK : LIGHT)
