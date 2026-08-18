# Arquitectura Técnica y Modelo de Datos — POS ark-dev
### v1.0 | Documento maestro para iniciar construcción con Claude Code

---

## Cómo usar este documento
Este es el blueprint técnico. Cuando empiecen con Claude Code a construir (no solo auditar), este documento —junto con `pos_especificacion_funcional.md` y `decisiones_post_auditoria.md`— va en el directorio de trabajo del repo nuevo. Define **qué** construir y **cómo organizarlo**; el código concreto lo escribe Claude Code apoyándose en esto, no al revés.

---

## 1. Principios de arquitectura (no negociables)

1. **Monolito modular, no microservicios.** Un solo backend Django, organizado en apps por dominio con límites claros — mismo patrón que ya usa `pharma_core` (`sales`, `inventory`, `organizations`...). Escalable a futuro sin la complejidad operativa que no necesitan hoy.
2. **Multi-tenancy relacional centralizado**, no schema-per-tenant. Aislamiento vía un mixin/queryset único, nunca filtros manuales repetidos por vista — esto es la lección más cara de la auditoría, no se repite en el repo nuevo.
3. **DRY con límites claros**: lo ya probado y estable (caja/turno, permisos, auditoría, reportes genéricos) se extrae como paquete compartido. Lo que necesita rediseño de dominio (catálogo, venta) se copia y rediseña directo aquí — no se abstrae prematuramente.
4. **No repetir el monolito de archivo único del frontend actual.** `POS.tsx` (1853 líneas) y `api.ts` (1613 líneas) fueron señalados como riesgo en la auditoría — el repo nuevo organiza por feature desde el día 1.
5. **Testing desde el inicio**, especialmente en frontend (hoy en cero) — no es opcional para el módulo de venta/caja/stock, donde la auditoría mostró que las reglas de negocio (concurrencia, unicidad de turno) sí están bien cubiertas en backend y vale la pena portar ese patrón.

---

## 2. Estructura de apps — Backend (Django)

| App | Responsabilidad | Origen |
|---|---|---|
| `core` | `TenantScopedQuerySet`/mixin, modelos base abstractos, utils compartidos | Nuevo |
| `tenants` | `Company`, `Branch`, `CompanySettings` (feature flags), `UserProfile`, roles/capabilities | Extraído + generalizado de `organizations` |
| `sales` | `CashRegister`, `CashShift`, `Sale`, `SaleDetail`, `Payment` | Extraído (caja) + rediseñado (venta) |
| `catalog` | `Product`, `Category`, `Supplier`, `Batch` (opcional), `StockTransfer`, `InventoryAdjustment` | Extraído + generalizado de `inventory` |
| `customers` | `Client`, `CreditAccount`, `CreditMovement` (fiado) | Nuevo |
| `audit` | `AuditLog` | Extraído tal cual |
| `billing` | Modelos stub de CFDI (sin lógica activa en MVP), gateado por feature flag | Nuevo, addon |

**Regla de límites entre apps:** ninguna app importa modelos de otra directamente para lógica de negocio — se comunican por servicios/interfaces claras (igual que hoy `sales` no debería tener lógica de `clinic` embebida; ese fue justo el problema encontrado). Si `sales` necesita algo de `catalog`, es un FK normal a nivel de modelo, pero la lógica de negocio de cada app vive en su propio `services.py`.

---

## 3. Estructura de features — Frontend (React)

Organizar por feature, no por tipo de archivo:

```
src/
  features/
    sales/          → carrito, checkout, ticket (reemplaza POS.tsx monolítico)
    shift/           → apertura/cierre de caja, arqueo
    catalog/         → CRUD de producto, categorías
    customers/       → clientes, fiado
    reports/
    admin/           → configuración de tenant, usuarios, roles
    vendor/          → panel super-admin (ya tiene base: VendorPanel/VendorRoute)
  services/
    api/
      salesApi.ts
      catalogApi.ts
      customersApi.ts
      authApi.ts      → (reemplaza el api.ts monolítico de 1613 líneas)
  lib/                → utils sin dependencia de dominio (reutilizable tal cual de pharma_front)
  components/ui/      → shadcn/Radix (reutilizable tal cual)
```

Cada feature es dueña de su propio estado (Context o similar, como ya usan) y su propio cliente API — nada de un solo archivo gigante que mezcle todos los dominios.

---

## 4. Modelo de datos

### 4.1 `tenants`

**Company** *(extraído de pharma_core, sin cambios de fondo)*
| Campo | Tipo | Nota |
|---|---|---|
| name | str | |
| tax_id | str | RFC del tenant (nullable — no todos tendrán CFDI activo) |
| is_active | bool | |

**Branch**
| Campo | Tipo | Nota |
|---|---|---|
| company | FK Company | |
| name | str | |
| address | str | |

**CompanySettings**
| Campo | Tipo | Nota |
|---|---|---|
| company | FK Company (1:1) | |
| enabled_modules | JSONField | `{'cfdi': false, 'multiple_branches': false, ...}` — reutilizado tal cual del patrón ya confirmado en la auditoría |

**UserProfile** — *cambio importante: login por email, no username*
| Campo | Tipo | Nota |
|---|---|---|
| user | FK a modelo de usuario custom (`AUTH_USER_MODEL`, con `email` como `USERNAME_FIELD`) | Decisión tomada tras encontrar la colisión de username global en la auditoría |
| branch | FK Branch | |
| role | choices: `CAJERO`, `ADMINISTRADOR` | Se quita `DOCTOR`/`RECEPTIONIST` (clínica); Super-admin **no** vive aquí, es `is_staff`/`is_superuser` a nivel Django |
| capabilities | JSONField | incluye `handles_cash` (reutilizado) y **`can_authorize_exceptions`** (nuevo — así se modela Supervisor, no como role aparte) |

**Nota de super-admin/soporte:** agregar `SupportAccessLog` (o extender `AuditLog`) para registrar cuándo un `is_staff` accede a datos de un tenant en modo soporte — gap identificado en la auditoría, pendiente de decidir si entra en MVP o fase 2 (ver sección 7).

**Decisión tomada durante construcción (confirma comportamiento mientras `SupportAccessLog` no existe):** `is_staff`/`is_superuser` **no** es un bypass automático del aislamiento a nivel API. Un usuario staff/superuser sin `UserProfile` ve listas vacías en los endpoints tenant-scoped (no 403, no acceso total); con `UserProfile` queda tan limitado como cualquier usuario normal. La única vía con visibilidad cross-tenant real hoy es Django Admin (`Model.objects.all()` sin filtrar, gateado por `is_staff` a nivel framework) — consistente con la regla de `CLAUDE.md` de que el admin de Django es solo para uso interno de desarrollo. Este comportamiento está fijado por tests (`tenants/tests/test_isolation.py::StaffAndSuperuserAccessTests`) y es el estado correcto hasta que se construya `SupportAccessLog`.

### 4.2 `sales`

**CashRegister** / **CashShift** — *extraídos casi sin cambios, ya genéricos*

**Decisión tomada durante construcción:** el override de "cerrar el turno de otro cajero" (en `pharma_core` estaba fijo a `role == ADMIN`) cambia aquí a `role == ADMINISTRADOR` **o** `capabilities.can_authorize_exceptions == True`. Es consistente con la decisión ya tomada en la sección 5 (Supervisor se modela como capability, no como role) — esto le da un uso real y probado a `can_authorize_exceptions` antes de que exista el endpoint de PIN (orden de construcción, punto 6). Ambos caminos (admin y capability) quedan registrados en `AuditLog`. **Actualizado al construir el punto 4**: `compute_expected_totals()` ya no solo cuenta el fondo de apertura — ahora suma `Payment` reales del turno (`CASH` al efectivo esperado, `CARD`/`TRANSFER` al voucher esperado; `CREDIT` no entra a ninguna de las dos sumas porque el fiado no mueve dinero en caja al momento de la venta).

**Sale/SaleDetail/Payment — rediseño real, punto 4 del orden de construcción.** Antes de codificar se decidieron y documentaron (no en silencio) los 3 puntos que quedaron abiertos en la v1 de este documento:

1. **Cantidad para KG/LITRO/GRAMO**: `SaleDetail.quantity` es `DecimalField(max_digits=10, decimal_places=3)` desde el modelo inicial, no un placeholder — 3 decimales cubre gramos como unidad mínima de kg/litro (ej. `0.750` kg). Se usa el mismo tipo para todos los `unit_type`, incluyendo PIEZA/PAQUETE/SERVICIO (`3.000`), para no tener dos tipos de columna condicionales.
2. **`tax_amount` por línea, no solo a nivel de Sale**: `SaleDetail` gana un campo `tax_amount` (no estaba en la tabla original de este documento) calculado y persistido al crear la venta; `Sale.tax_amount` es la suma de sus líneas. Razón: la especificación (§7) exige exenciones tipo "alimentos básicos" — dos líneas de la misma venta pueden tener tasas de IVA distintas, y sumar el impuesto solo al total perdería esa granularidad. `SaleDetail.tax_rate_applied` congela `Product.tax_rate` al momento de la venta (si el producto cambia de tasa después, no reescribe ventas ya cerradas). No hay descuento por línea (`discount_amount` sigue siendo solo de `Sale`, tal como ya estaba en la tabla original) — el impuesto se calcula sobre el subtotal bruto de cada línea, no sobre un neto post-descuento que no existe a ese nivel.
3. **`client_uuid` (unique) y `occurred_at` confirmados desde ahora**: ambos van en `Sale` desde el modelo inicial aunque la cola de sincronización offline no se construya todavía, tal como ya pedía este documento. `client_uuid` no tiene `default` a nivel de modelo (lo genera el cliente offline, no el servidor) — `sales.services.create_sale` sí genera uno server-side si no llega, para no bloquear el flujo síncrono de hoy.

**Decisiones adicionales tomadas con el mismo criterio de core/tenants/audit/catalog, no preguntadas explícitamente:**
- **`Sale.client` (FK a `customers.Client`, para fiado) queda fuera del modelo por ahora** — `customers` es el punto 5 del orden de construcción, todavía no existe, y no se puede apuntar un FK a un modelo inexistente. `Payment.method = CREDIT` ya existe como choice (no depende de `customers`), pero su contabilidad real (cargar a `CreditAccount`) se conecta cuando `customers` exista. Se retoma en el punto 5, igual que "reportes genéricos" se documentó como pospuesto en `decisiones_post_auditoria.md` §10.
- **Descuento de stock por lote vive en `catalog.services.decrement_batch_stock`, no en `sales`** — `sales.services.create_sale` lo llama en vez de tocar `Batch` directamente, respetando la regla de límites entre apps de la sección 2 ("si `sales` necesita algo de `catalog`, es un FK normal a nivel de modelo, pero la lógica de negocio vive en su propio `services.py`"). Usa `select_for_update()` con hilos reales probados en test — mismo patrón que la concurrencia de apertura de turno, y el que la sección 8 ya pedía portar de `deduct_stock_fefo`. No hace selección FEFO automática: el lote ya viene elegido por quien llama (`SaleDetail.batch` es explícito, no auto-asignado) — FEFO automático queda como posible mejora futura, no pedida todavía.
- **`TenantScopedFieldsMixin` no se usa en los serializers anidados de líneas/pagos** (`SaleLineInputSerializer`, `PaymentInputSerializer`) — un serializer anidado declarado como atributo de clase (`details = XSerializer(many=True)`) se instancia una sola vez al importar el módulo, sin `request` disponible todavía, así que el mixin no tendría nada que acotar (el `context` con el `request` real solo llega después, vía `bind()`). `product_id`/`batch_id` se resuelven a mano contra `.objects.for_user(...)` en el ViewSet — mismo patrón ya usado en `OpenShiftInputSerializer.cash_register_id`. El mixin sí se usa en el campo top-level `cash_shift` de `SaleCreateSerializer`, que sí se instancia una vez por request con contexto real.

**Sale**
| Campo | Tipo | Nota |
|---|---|---|
| branch, cash_register, cash_shift | FKs | `cash_shift` es el nombre real del modelo de turno (`CashShift`, no `Shift`) — `branch`/`cash_register` se guardan denormalizados, derivados de `cash_shift` en `save()` |
| client | — | **Pendiente, ver nota arriba** — no existe hasta el punto 5 (`customers`) |
| client_uuid | UUID, unique | Idempotencia para offline — sin default de modelo, ver punto 3 arriba |
| occurred_at | datetime | Distinto de `created_at`, lo declara el cliente — ver punto 3 arriba |
| created_at | datetime (auto_now_add) | Cuándo llegó al servidor |
| subtotal, discount_amount, tax_amount, total | Decimal | `tax_amount` es la suma de `SaleDetail.tax_amount` — ver punto 2 arriba |
| status | choices: `COMPLETED`, `CANCELLED`, `REFUNDED` | |

**SaleDetail**
| Campo | Tipo | Nota |
|---|---|---|
| sale | FK Sale | |
| product | FK Product | |
| batch | FK Batch, **nullable** | Cambio clave: ya no obligatoria |
| quantity | Decimal(10,3) | Fraccionaria — ver punto 1 arriba |
| unit_price, tax_rate_applied | Decimal | |
| tax_amount | Decimal | **Agregado en construcción, no estaba en la tabla original** — ver punto 2 arriba |

**Payment** *(nuevo — habilita pago dividido, no existía en Zenith Pharma)*
| Campo | Tipo | Nota |
|---|---|---|
| sale | FK Sale | |
| method | choices: `CASH`, `CARD`, `TRANSFER`, `CREDIT` | `CREDIT` no cuenta en el arqueo de caja (ver nota de `compute_expected_totals` arriba) ni tiene contabilidad de fiado todavía (pendiente de `customers`) |
| amount | Decimal | Una venta puede tener N registros Payment que suman el total — `sales.services.create_sale` rechaza toda la venta (rollback completo) si no suman exacto |

### 4.3 `catalog`

**Product** — *generalizado, sin campos de farmacia*
| Campo | Tipo | Nota |
|---|---|---|
| name, sku, barcode | str | |
| category, supplier | FKs | Reutilizados tal cual |
| unit_type | choices: `PIEZA`, `KG`, `GRAMO`, `LITRO`, `PAQUETE`, `SERVICIO` | Generaliza granel + papelería + servicios (fotocopias, etc.) |
| requires_batch | bool | Reemplaza la obligatoriedad — FEFO se vuelve opcional por producto |
| variant_attributes | JSONField, nullable | Color/talla para papelería, sin tabla de variantes rígida en v1 |
| cost_price, sale_price | Decimal | |
| tax_rate | Decimal | Reemplaza `tax_percentage` huérfano — este sí se conecta al cálculo real |
| min_stock | int | |
| **image** | **ImageField, nullable** | **Agregar desde el diseño aunque no se use en MVP** — evita migración de "URL en texto" a archivo real más adelante. Storage backend: Azure Blob vía `django-storages`, prefijo por tenant (`tenant_{id}/products/...`) |

**Category, Supplier** — extraídos con un ajuste: `company` no-nullable (consistente con la regla del proyecto de que todo dato de tenant tiene su company explícita, sin excepción por conveniencia).

**Batch** — extraído con dos ajustes deliberados sobre `pharma_core`: `branch` ya no nullable, y se agregó `UniqueConstraint(product, batch_number)` a nivel de base de datos — en `pharma_core` esa unicidad era solo una regla de dominio no forzada, aquí se cierra a nivel constraint.

**StockTransfer, InventoryAdjustment** — extraídos tal cual, sin cambios de fondo (pendientes de construir).

**Confirmado sin ambigüedad durante construcción:** `Product.unit_type` es únicamente un campo de choices informativo — no tiene lógica de venta a granel embebida. Esa lógica (cómo se captura/valida una venta por KG/LITRO, integración de báscula si aplica) pertenece 100% a `sales`, no a `catalog`. `requires_batch` es igualmente informativo: no hay constraint de BD que ate `Product` a `Batch` en ningún sentido — lo confirma `RequiresBatchIndependenceTests`, que prueba las 4 combinaciones posibles.

### 4.4 `customers` *(100% nuevo)*

**Client**
| Campo | Tipo | Nota |
|---|---|---|
| branch/company | FK | |
| name, phone | str | |
| credit_limit | Decimal | |

**CreditAccount**
| Campo | Tipo | Nota |
|---|---|---|
| client | FK Client (1:1) | |
| balance | Decimal | |

**CreditMovement**
| Campo | Tipo | Nota |
|---|---|---|
| account | FK CreditAccount | |
| sale | FK Sale, nullable | Nullable porque un abono no viene de una venta |
| amount, type (`CARGO`/`ABONO`) | | |

### 4.5 `audit` — extraído tal cual, sin cambios.

---

## 5. Patrón de aislamiento multi-tenant (crítico)

Un solo mecanismo, usado por **todas** las apps, sin excepción:

```
TenantScopedQuerySet / TenantScopedManager
  → filtra automáticamente por company/branch del usuario autenticado
  → cada modelo con datos de tenant hereda de un BaseTenantModel en `core`
  → los ViewSets NO implementan su propio get_queryset() con filtro manual
```

Esto reemplaza el patrón de `pharma_core` (filtro manual repetido por ViewSet) que la auditoría marcó como riesgo. Es la primera pieza de infraestructura a construir — todo lo demás depende de que esto exista y esté bien probado (con tests que confirmen que un tenant no puede ver datos de otro, no solo que el happy path funciona).

**Pieza agregada durante construcción, ahora parte del patrón:** `core/serializers.py::TenantScopedFieldsMixin` — acota los querysets de campos FK en serializers (ej. `branch`, `category`, `supplier`) al tenant del request. Nace de un vector de fuga encontrado dos veces por separado (`CashRegisterSerializer.branch`, luego `Product.category`/`.supplier` y `Batch.product`/`.branch`): sin esto, un FK sin acotar en un serializer permite crear/editar un registro apuntando a datos de otro tenant, aunque el queryset de lectura ya esté filtrado por `TenantScopedQuerySet`. **Regla derivada: todo serializer con un campo FK debe usar este mixin, no es opcional ni caso por caso** — el aislamiento a nivel API no está completo solo con el queryset de lectura, también hay que acotar lo que se puede *escribir*.

---

## 6. Convenciones de API

- REST estándar sobre DRF, autenticación JWT (reutilizado — `SimpleJWT` ya está probado en producción).
- Login por **email**.
- Versionado desde el inicio: `/api/v1/...` (evita romper el frontend cuando haya `/v2` a futuro).
- Paginación por default en todos los listados.
- Endpoint nuevo a futuro (no en MVP, pero dejar el nombre reservado): `POST /api/v1/sales/sync-batch/` para la cola offline.
- Errores en formato consistente (código + mensaje) desde el día 1 — no default de DRF sin estandarizar.

---

## 7. Seguridad

- Secrets en **Azure Key Vault**, nunca en variables de entorno planas ni en código (ya está en el checklist de Carlos).
- PIN/reautenticación para `can_authorize_exceptions`: endpoint separado que valida credenciales del supervisor sin cerrar la sesión del cajero — greenfield, confirmado en la auditoría que no existe nada parecido hoy.
- `SupportAccessLog` para accesos de super-admin en modo soporte — **decisión pendiente**: ¿entra en MVP o se pospone? Mi recomendación: se puede posponer con seguridad mientras solo tú/Carlos tengan acceso de staff y sea 1 cliente — pero antes de dar acceso de soporte a datos de un tercer/cuarto cliente, ya debería existir.

---

## 8. Testing

- Backend: portar las *reglas* de los tests existentes (`sales/tests.py`, `inventory/tests.py`, `organizations/tests.py`) adaptadas al nuevo modelo — concurrencia en descuento de stock, unicidad de turno abierto, reconciliación de cierre de caja.
- Backend: tests obligatorios para el aislamiento multi-tenant (sección 5) — no es opcional, es la pieza de mayor riesgo de seguridad del sistema.
- Frontend: empezar a meter tests donde no había ninguno — mínimo para `features/sales` y `features/shift`, que es donde vive el dinero.

---

## 9. Orden de construcción sugerido

1. `core` (TenantScopedQuerySet) + `tenants` (Company/Branch/UserProfile con login por email) — la base de la que depende todo.
2. Extracción de piezas "tal cual" (`audit`, permisos, `CashRegister`/`CashShift`, reportes genéricos, feature flags) como paquete compartido.
3. `catalog` (Product generalizado, con `image` desde el diseño aunque no se use aún).
4. `sales` (Sale/SaleDetail/Payment rediseñados — pago dividido, impuestos reales, `client_uuid`/`occurred_at` en el modelo aunque la cola de sync no se construya todavía).
5. `customers` (fiado) — greenfield.
6. Capability `can_authorize_exceptions` + endpoint de PIN — greenfield.
7. Frontend: features de venta/caja primero (son el corazón del uso diario), catálogo y clientes después.
8. Integración de hardware en tienda real + pruebas con el cliente.
9. (Post-MVP) Cola de sincronización offline completa, `SupportAccessLog`, CFDI.

---

## 10. Pendiente de decisión antes de codificar

- [ ] ¿`variant_attributes` como JSONField es suficiente para papelería en v1, o el cliente ya tiene casos concretos (ej. muchas tallas/colores) que ameriten una tabla de variantes propia desde ahora?
- [ ] Confirmar con Carlos: subdominio propio por cliente vs. login único con selector — afecta cómo se configura DNS/SSL, pendiente del checklist que ya le pasamos.
- [ ] Política de conflicto de stock para cuando se construya la sync offline (venta en negativo + alerta, vs. bloqueo) — sigue siendo decisión de negocio, no técnica.
