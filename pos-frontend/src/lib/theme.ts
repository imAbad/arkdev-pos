const ACCENT_VAR = '--color-accent'
const DEFAULT_ACCENT = '#1e5b94'

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/

/** Aplica accent_color del tenant (CompanySettings) a la variable CSS que
 * usan los estilos de marca/navegación (nunca los botones de acción —
 * ver index.css). Si el tenant no lo configuró o el valor es inválido,
 * usa el azul de referencia por default. */
export function applyAccentColor(accentColor: string | null | undefined): void {
  const value = accentColor && HEX_COLOR.test(accentColor) ? accentColor : DEFAULT_ACCENT
  document.documentElement.style.setProperty(ACCENT_VAR, value)
}
