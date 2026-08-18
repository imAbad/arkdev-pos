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

### 4.2 `sales`

**CashRegister** / **CashShift** — *extraídos casi sin cambios, ya genéricos*

**Sale**
| Campo | Tipo | Nota |
|---|---|---|
| branch, cash_register, shift | FKs | |
| client | FK Client, nullable | Para venta con fiado |
| client_uuid | UUID, unique | **Nuevo — idempotencia para offline** |
| occurred_at | datetime | **Nuevo — distinto de `created_at`, lo declara el cliente** |
| created_at | datetime (auto_now_add) | Cuándo llegó al servidor |
| subtotal, discount_amount, tax_amount, total | Decimal | El cálculo de impuestos se construye desde cero (confirmado que `tax_percentage` no se usaba en Zenith Pharma) |
| status | choices: `COMPLETED`, `CANCELLED`, `REFUNDED` | |

**SaleDetail**
| Campo | Tipo | Nota |
|---|---|---|
| sale | FK Sale | |
| product | FK Product | |
| batch | FK Batch, **nullable** | Cambio clave: ya no obligatoria |
| quantity, unit_price, tax_rate_applied | Decimal | |

**Payment** *(nuevo — habilita pago dividido, no existía en Zenith Pharma)*
| Campo | Tipo | Nota |
|---|---|---|
| sale | FK Sale | |
| method | choices: `CASH`, `CARD`, `TRANSFER`, `CREDIT` | |
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

**Category, Supplier, Batch, StockTransfer, InventoryAdjustment** — extraídos tal cual, sin cambios de fondo.

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
