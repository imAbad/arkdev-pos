# Decisiones y Hallazgos Post-Auditoría — Arquitectura del Nuevo POS
### ark-dev | Consolida auditoría 16 ago 2026 + addendum 17 ago 2026 (v3)

> **Nota de proceso:** este documento reemplaza a la v1. A partir de ahora es la única fuente de verdad de decisiones — evita depender de que Claude Code tenga acceso a varios archivos sueltos; con este solo basta.

---

## 1. El hallazgo más importante

La jerarquía **Company → Branch → CashRegister → CashShift** ya existe en `pharma_core` y coincide con lo que pedía la especificación (**Tenant → Sucursal → Caja**), incluyendo reportes por caja/sucursal/tenant. Confirmado sin cambios en ambas pasadas.

**Decisión de tenant tomada:** *no* migrar a schema-per-tenant (`django-tenants`). A 1-5 tenants/año, el costo operativo (migración por schema, routing de conexión, backups por schema) no se justifica frente a lo que ya funciona. Se construye un **`TenantScopedQuerySet`/mixin centralizado** sobre el modelo FK actual (`Company`/`Branch`), reemplazando el filtro manual repetido por ViewSet — mismo nivel de aislamiento, sin el costo de infraestructura.

---

## 2. Se extrae YA como paquete compartido (bajo riesgo, listo para formalizar)

| Pieza | Por qué es seguro extraerlo ahora |
|---|---|
| Bitácora de auditoría (`apps/audit`) | Agnóstica de dominio, sin cambios de esquema necesarios |
| Patrón de permisos (capability JSON + permission classes DRF) | Solo hay que renombrar roles/módulos, la arquitectura ya sirve |
| `CashRegister` / `CashShift` + apertura/cierre/arqueo ciego (backend) | Sin acoplamiento a farmacia detectado |
| Reportes genéricos (producto, valuación de inventario, mermas) | Consultas ya parametrizadas por fecha/sucursal, sin campos de farmacia |
| UI kit (shadcn/Radix, utils, patrón de refresh JWT) | Sin dependencia de dominio |
| **`CompanySettings.enabled_modules`** (feature flags por tenant) | **Confirmado en la 2ª pasada: es exactamente el mecanismo de plan/addon que se necesita para activar CFDI por tenant sin migración de esquema — solo agregar la clave.** |
| **Endpoints base de panel Super-admin** (`CompanyListView`, `CompanySettingsView`, rama vendor de `UserContextView`) | **Confirmado en la 2ª pasada (antes "pendiente"): sí hay respaldo real en backend, gateado `IsAdminUser`/`is_staff`, y `VendorPanel.tsx` ya los consume.** Reutilizable como base, aunque falta la bandera de "modo soporte" auditado (ver sección 4). |

## 3. Se copia y se rediseña directo en el nuevo repo (no se comparte todavía)

| Pieza | Qué hay que quitarle/agregarle |
|---|---|
| Catálogo de producto | Separar campos genéricos de campos 100% farmacia (lote, caducidad, receta); agregar variantes/granel/servicios |
| Carrito / venta | Quitar FKs directas a `clinic.Prescription`/`Consultation`; agregar descuento visible y pago dividido; **construir cálculo de impuestos desde cero** (ver sección 5) |
| Ticket de venta | Generalizar el render, hoy está atado al flujo de farmacia |
| Lote / caducidad (FEFO) | Hacerlo **opcional** por producto, no obligatorio en cada línea de venta |

*Razón para no formalizar estas en un paquete compartido todavía: el modelo de retail (catálogo, venta, pago) aún no existe — abstraer antes de tener un segundo caso real de uso sería prematuro.*

## 4. Se construye desde cero (no existe nada reutilizable)

- **Clientes y crédito ("fiado")** — confirmado con búsqueda extendida a las 6 apps del proyecto: cero modelo, cero lógica, cero UI en ninguna parte de Zenith Pharma.
- **Capa de resiliencia offline** — greenfield, ahora acotado a 4 piezas concretas (no "greenfield" genérico):
  1. `client_uuid` por venta (deduplicación/idempotencia — hoy el folio lo genera el servidor, no depende de nada del cliente).
  2. `occurred_at` distinto de `created_at` (hoy `Sale.created_at` es `auto_now_add`, reloj del servidor únicamente).
  3. Endpoint de sincronización batch (ej. `POST /api/sales/sync-batch/`) que procese un arreglo de ventas encoladas idempotentemente por `client_uuid` — no existe, `SaleViewSet.create` solo procesa una venta síncrona a la vez.
  4. Política de conflicto de stock al sincronizar (venta en negativo + alerta, vs. bloqueo) — **esta es decisión de negocio pendiente, no técnica**; el patrón transaccional existente (`select_for_update()` en `deduct_stock_fefo`) sirve de base para cualquiera de las dos opciones.
- **Aislamiento multi-tenant centralizado a nivel API** — el patrón actual (filtro manual por ViewSet) **no se debe copiar tal cual**; construir `TenantScopedQuerySet` desde el diseño del nuevo repo.
- **PIN / segundo factor para autorizar excepciones** — la especificación (§2, §13) exige reautenticación puntual del supervisor para descuentos fuera de política, cancelaciones, devoluciones. Búsqueda dirigida en `pharma_core`: no existe ningún mecanismo de este tipo. Es trabajo nuevo de punta a punta.
- **Bandera de "modo soporte" auditado para Super-admin** — la especificación pide que el proveedor normalmente no vea datos de venta del tenant salvo con fines de soporte explícito. Hoy `is_staff`/`is_superuser` es binario, sin distinguir "modo soporte" ni dejar rastro de cuándo se accedió. Trabajo nuevo pero acotado (se apoya en `apps/audit`, que sí es reutilizable).
- **Cálculo real de impuestos** — confirmado con evidencia de código: `tax_percentage` existe en `Product`, se serializa y administra, pero **nunca se usa** en `SaleDetail.save()` (que solo calcula `unit_price * quantity`). Es un campo huérfano/stub — el cálculo de IVA (incluyendo exenciones tipo alimentos básicos, §7) se construye desde cero, no se "activa".

---

## 5. Decisiones de arquitectura — ya tomadas

- **Resolución de tenant**: confirmado, login-por-usuario (no subdominio) es suficiente y más simple para 1-5 clientes/año — decisión explícita, no por inercia.
- **Identificador de login**: **usar email como identificador único de login en el nuevo repo, no username.** Hallazgo nuevo de la 2ª pasada: `pharma_core` usa `username` global (no por compañía) — dos tenants no podrían tener ambos un usuario `cajero1`. No bloquea con 1 cliente, pero es fricción real de onboarding con el segundo. El nuevo repo evita este problema desde el diseño usando email (naturalmente único) en vez de heredar el patrón de username.
- **Rol Supervisor**: **se modela como capability `can_authorize_exceptions`, no como un cuarto valor de `role`.** Los permisos de Supervisor son aditivos sobre Cajero (todo lo del cajero + autorizar excepciones), no una categoría paralela — mismo patrón que ya usa el repo para `handles_cash`.
- **Panel Super-admin**: confirmado que ya existe respaldo backend real (ver sección 2). Pendiente decidir si la bandera de "modo soporte" auditado entra en el MVP o se pospone — no es bloqueante para el primer cliente, sí es relevante antes de dar acceso de soporte a datos de más clientes.

## 6. Verificaciones que quedaron cerradas (ya no son supuestos)

| Pregunta original | Resultado |
|---|---|
| ¿`tax_percentage` se usa en el cálculo? | **No** — stub sin usar, confirmado con evidencia de código |
| ¿Hay algo de "fiado" en alguna app? | **No** — búsqueda extendida a las 6 apps, cero resultados |
| ¿Hay algún gancho para CFDI? | **Parcial** — no hay captura fiscal por venta, pero hay un comentario de diseño explícito en `apps/sales/models.py` que ya separa `consultation` de `Product`/`SaleDetail` justo para no complicar la clasificación fiscal de cara a CFDI. Buena señal: el principio "documento de venta interno primero, CFDI como capa después" (que ya recomendaba la especificación §12) no es ajeno al equipo — vale la pena mantenerlo explícito al diseñar el nuevo `Sale`. |
| ¿`VendorPanel` tiene respaldo backend? | **Sí** — confirmado con endpoints reales (ver sección 2) |

---

## 7. Estrategia de extracción — confirmada

**Opción C: copiar y desacoplar para el MVP**, con extracción temprana parcial:
- Las piezas de la sección 2 (bajo riesgo, ya estables — incluye feature flags y base del panel Super-admin) se extraen ahora como paquete Git privado.
- Las piezas de la sección 3 (catálogo, venta, pago, ticket) se copian y rediseñan directo en el nuevo repo — formalizarlas en un paquete compartido se revisita **después** de que el segundo cliente de retail esté en producción y el modelo haya demostrado estabilidad.

*Activo a rescatar, no solo código:* las suites de tests del backend (`sales/tests.py`, `inventory/tests.py`, `organizations/tests.py`) codifican reglas de negocio ya probadas. Vale la pena portar esas *reglas* (adaptando los tests) al nuevo repo, no solo copiar el código.

## 8. Riesgo a vigilar en el nuevo repo

El repo actual no tiene tests en frontend y concentra la lógica de venta/caja en dos archivos monolíticos (`POS.tsx` 1853 líneas, `api.ts` 1613 líneas). Al copiar y desacoplar hacia el nuevo repo, es el momento natural de **no repetir ese patrón** — separar por feature desde el inicio.

---

## 9. Próximo paso sugerido

Ya no quedan supuestos importantes abiertos sobre el código existente. Con esto hay suficiente para definir el **modelo de datos concreto** del nuevo repo:
- `Product` sin campos de farmacia, con variantes/granel/servicios
- `Sale` con pago dividido, descuento visible, y cálculo de impuestos real (construido desde cero)
- `Client`/`Fiado` nuevo (saldo, límite de crédito, abonos)
- `TenantScopedQuerySet` centralizado
- Campos de idempotencia para offline (`client_uuid`, `occurred_at`) + endpoint `sync-batch`
- Capability `can_authorize_exceptions` + mecanismo de PIN/reautenticación
- Login por email (no username)

Es el siguiente documento natural antes de escribir la primera línea de código.
