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

**Decisión tomada durante construcción:** el override de "cerrar el turno de otro cajero" (en `pharma_core` estaba fijo a `role == ADMIN`) cambia aquí a `role == ADMINISTRADOR` **o** `capabilities.can_authorize_exceptions == True`. Es consistente con la decisión ya tomada en la sección 5 (Supervisor se modela como capability, no como role) — esto le da un uso real y probado a `can_authorize_exceptions` antes de que exista el endpoint de PIN (orden de construcción, punto 6). Ambos caminos (admin y capability) quedan registrados en `AuditLog`. `expected_closing_balance` en el arqueo hoy solo contempla el fondo de apertura, porque `Sale`/`Payment` no existen todavía (punto 4) — `compute_expected_totals()` es el único punto a extender cuando lleguen.

**Sale** — *construido; ver decisiones reales abajo*
| Campo | Tipo | Nota |
|---|---|---|
| branch, cash_register, shift | FKs | |
| client | FK Client, nullable | **Construido en el punto 5** (ver §4.4) — obligatorio solo si algún `Payment` de la venta es `CREDIT`. |
| client_uuid | UUID, unique | Confirmado en el modelo desde ahora, sin default a nivel modelo |
| occurred_at | datetime | Distinto de `created_at`, lo declara el cliente |
| created_at | datetime (auto_now_add) | Cuándo llegó al servidor |
| subtotal, discount_amount, total | Decimal | |
| tax_amount | Decimal | **Es la suma de `SaleDetail.tax_amount`, no un cálculo independiente** — ver decisión abajo |
| status | choices: `COMPLETED`, `CANCELLED`, `REFUNDED` | |

**SaleDetail** — *construido, con un campo agregado sobre el diseño original*
| Campo | Tipo | Nota |
|---|---|---|
| sale | FK Sale | |
| product | FK Product | |
| batch | FK Batch, **nullable** | Cambio clave: ya no obligatoria |
| quantity | **Decimal(10,3)** | Decidido así desde el modelo inicial (no placeholder) — cubre fracciones como 0.750 kg para productos `unit_type` KG/LITRO/GRAMO |
| unit_price, tax_rate_applied | Decimal | |
| **tax_amount** | **Decimal — agregado, no estaba en el diseño original** | **Decisión tomada durante construcción**: el IVA se calcula y guarda **por línea**, no solo a nivel `Sale`. Razón: la especificación exige exenciones tipo alimentos básicos — dos líneas de la misma venta pueden tener tasas distintas (ej. un producto exento + uno gravado), y sumar solo al total pierde esa granularidad para auditoría/corrección posterior. `Sale.tax_amount` es la suma de las líneas, no un cálculo aparte. |

**Descuento de stock — vive en `catalog`, no en `sales`:** `catalog.services.decrement_batch_stock()`, con `select_for_update()` probado con hilos reales (mismo patrón de concurrencia que `CashShift`). Se puso en `catalog` y no en `sales` para respetar el límite de apps de la sección 2 (`sales` no debe importar lógica de negocio de otra app directamente) — `sales` llama al servicio de `catalog`, no reimplementa el descuento.

**Payment** *(nuevo — habilita pago dividido, no existía en Zenith Pharma)*
| Campo | Tipo | Nota |
|---|---|---|
| sale | FK Sale | |
| method | choices: `CASH`, `CARD`, `TRANSFER`, `CREDIT` | `CREDIT` conectado con `customers` desde el punto 5 — ver §4.4 |
| amount | Decimal | Una venta puede tener N registros Payment que suman el total |

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

### 4.4 `customers` — construido (punto 5)

**Client**
| Campo | Tipo | Nota |
|---|---|---|
| company | FK | **Decisión tomada durante construcción**: escalado por `company`, no por `branch` — la tabla original era ambigua en esto. Razón: un cliente con fiado compra típicamente en cualquier sucursal del mismo negocio, no queda amarrado a una; si el tenant abre una segunda sucursal, el cliente y su saldo de crédito deben seguir siendo los mismos, no duplicarse por sucursal. |
| name, phone | str | |
| credit_limit | Decimal | **No es decorativo** — ver `charge_credit` abajo, se valida antes de mutar cualquier dato |

**CreditAccount**
| Campo | Tipo | Nota |
|---|---|---|
| client | FK Client (1:1) | Se crea automáticamente al crear el `Client` — nunca queda un `Client` sin `CreditAccount` |
| balance | Decimal | |

**CreditMovement** — anidado en `CreditAccount`, sin ViewSet propio (se crea vía `CreditAccountViewSet.pay` o automático desde `sales`)
| Campo | Tipo | Nota |
|---|---|---|
| account | FK CreditAccount | |
| sale | FK Sale, nullable | Nullable porque un abono (`ABONO`) no viene de una venta — confirmado por test dedicado que un abono sin venta actualiza `balance` correctamente |
| amount, type (`CARGO`/`ABONO`) | | |

**Integración con `sales` (cierra el pospuesto del punto 4):** `Sale.client` ya está conectado — nullable, obligatorio solo cuando algún `Payment` es `CREDIT`. `create_sale` llama a `customers.services.charge_credit` por el monto a crédito, **dentro de la misma transacción** que la venta. **Si `credit_limit` se excede, el rollback es completo: la venta entera se revierte, incluyendo el descuento de stock, no solo el cargo de crédito.** Esta garantía (transaccionalidad de punta a punta, no solo del pago) es más estricta que lo que el blueprint especificaba explícitamente — queda fijada por tests y es el comportamiento esperado de aquí en adelante, no algo a relajar sin decisión explícita.

**Excepción real a la regla de `TenantScopedFieldsMixin` en anidados (sección 5):** `CreditMovementInputSerializer.sale_id` se resuelve a mano (es un serializer anidado) — probado que un `sale_id` de otro tenant da 404 sin tocar el balance. `CreditAccountSerializer.client` sí usa el mixin normalmente, porque es un campo top-level, no anidado — confirma que la regla se aplicó con criterio, no de forma mecánica.

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

**Límite conocido del mixin, encontrado en `sales` — aplica a cualquier app futura con serializers anidados:** `TenantScopedFieldsMixin` **no funciona en serializers declarados como atributo de clase dentro de otro serializer** (el `request` no existe todavía en su `__init__` en ese punto de la carga). En `SaleDetail` (anidado dentro de `Sale`), `product_id`/`batch_id` se resuelven a mano en vez de vía el mixin; el mixin sí se usa en el campo top-level (`cash_shift`). **Regla para cualquier app futura:** si un serializer va anidado como atributo de clase, sus FKs se acotan a mano (con el mismo criterio de seguridad, solo que sin el mixin) — no asumir que "usar el mixin" alcanza solo porque el serializer lo importa. **Ya aplicada al construir `customers` (punto 5)** — ver el detalle en §4.4.

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
5. `customers` (fiado) — greenfield. ✅ Construido: `Client`/`CreditAccount`/`CreditMovement`, `Sale.client` conectado, `Payment.method=CREDIT` carga a `CreditAccount` (ver §4.4).
6. Capability `can_authorize_exceptions` + endpoint de PIN — greenfield.
7. Frontend: features de venta/caja primero (son el corazón del uso diario), catálogo y clientes después.
8. Integración de hardware en tienda real + pruebas con el cliente.
9. (Post-MVP) Cola de sincronización offline completa, `SupportAccessLog`, CFDI.

---

## 10. Pendiente de decisión antes de codificar

- [ ] ¿`variant_attributes` como JSONField es suficiente para papelería en v1, o el cliente ya tiene casos concretos (ej. muchas tallas/colores) que ameriten una tabla de variantes propia desde ahora?
- [ ] Confirmar con Carlos: subdominio propio por cliente vs. login único con selector — afecta cómo se configura DNS/SSL, pendiente del checklist que ya le pasamos.
- [ ] Política de conflicto de stock para cuando se construya la sync offline (venta en negativo + alerta, vs. bloqueo) — sigue siendo decisión de negocio, no técnica.
