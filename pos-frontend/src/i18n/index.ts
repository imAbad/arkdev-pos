import { es } from './strings'

// Agregar un idioma nuevo: crear ./strings.<locale>.ts con la misma forma
// que `es` (usar `Strings` para que TS avise si falta una clave) y elegirlo
// aquí — ningún componente cambia.
export const t = es
