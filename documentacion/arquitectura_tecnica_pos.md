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
pos-frontend/
  src/
    features/
      auth/            ✅ AuthProvider (token, profile, branch, company settings), LoginScreen
      shift/            ✅ OpenShiftScreen
      sales/             ✅ SaleScreen, ProductSearch, CartView, PaymentPanel, SaleConfirmation, cart.ts
      catalog/         → CRUD de producto, categorías — pendiente
      customers/       → clientes, fiado — pendiente
      reports/         → pendiente
      admin/           → configuración de tenant, usuarios, roles — pendiente
      vendor/          → panel super-admin — pendiente
    services/
      api/
        authApi.ts       ✅
        tenantsApi.ts     ✅ (me, branch, company-settings — no estaba en la lista original, se agregó al construir)
        salesApi.ts        ✅ (cash-registers, cash-shifts, create-sale)
        catalogApi.ts       ✅ (búsqueda de productos)
        customersApi.ts   → pendiente
    i18n/              ✅ strings.ts (español) + index.ts — ver nota de i18n abajo
    lib/               ✅ api-client, auth-storage, theme, format, utils — sin dependencia de dominio
    components/        ✅ app-header.tsx (identidad + logout), sidebar.tsx (nav role-aware), app-layout.tsx (layout de rutas — punto 13)
    components/ui/     ✅ button, input, label, card, confirm-dialog — Radix + Tailwind, NO se usó el CLI de shadcn (ver nota abajo)
    types/api.ts       ✅ tipos leídos de los serializers reales, no de esta documentación
```

Cada feature es dueña de su propio estado (Context o similar) y su propio cliente API — nada de un solo archivo gigante que mezcle todos los dominios.

### 3.1 Decisiones tomadas al arrancar el frontend (sesión de la primera pantalla)

- **`components/ui/` es Radix + Tailwind con estilos propios, no shadcn CLI**: el brief de diseño pide botones grandes y táctiles (mín. 56px de alto) para personal con poca práctica en pantallas táctiles — el tamaño compacto por default de shadcn no encaja, y correr el CLI para luego sobreescribir cada tamaño no aportaba sobre construir el componente directo con Radix (`@radix-ui/react-*`) + `class-variance-authority` + Tailwind, que es exactamente lo que el CLI genera de cualquier forma. Sigue siendo "shadcn/Radix" en el sentido de la sección 3 original (mismas piezas, mismo patrón de composición), no una librería de componentes distinta.
- **React Router (`react-router-dom`) agregado en el punto 13 de esta sesión** — hasta ahí el flujo era lineal (login → abrir turno → vender) y bastaba un estado simple en `App.tsx` (`status` de auth + `shift` actual, sin rutas); con 6 pantallas de administración (reportes, módulos, catálogo/relacionados, stock bajo, usuarios, mi negocio) además de vender, ese hack (`NavigationContext`/`ViewKey` a mano) ya no alcanzaba — exactamente el momento que esta nota ya anticipaba. `App.tsx` define rutas reales bajo un único `AppLayout` (`components/app-layout.tsx`: `Sidebar` + `AppHeader` + `<Outlet/>`); `Sidebar` (`components/sidebar.tsx`) es role-aware (`isAdministrator`/`isAdministratorOrSupervisor`, mismo criterio ya usado en el backend). El flujo de venta (`/`: abrir turno → vender → cerrar turno → ticket) sigue viviendo dentro de esa misma ruta raíz, sin cambios de comportamiento — el router solo reemplaza cómo se llega a las OTRAS pantallas. Guards de rol por ruta (`RequireAdmin`/`RequireAdminOrSupervisor` en `App.tsx`) son solo UX (evitan un 403 crudo si alguien escribe la URL a mano) — el control de acceso real sigue siendo el backend.
- **i18n centralizado en `src/i18n/strings.ts`**: un solo objeto anidado con todo el texto visible de la app; ningún componente escribe un string suelto. Hoy solo existe `es` (español); agregar un idioma nuevo es crear `strings.<locale>.ts` con la misma forma (TypeScript avisa si falta una clave, por el tipo `Strings` exportado) y elegirlo en `i18n/index.ts` — no toca ningún componente. Esto es directamente la corrección al problema que la auditoría encontró en `pharma_frontend` (strings de farmacia repartidos sin i18n en 9 archivos).
- **Colores con significado fijo, no por componente**: verde (`confirm`) para cualquier acción de "avanzar/confirmar" (Entrar, Abrir turno, Agregar, Cobrar), rojo (`cancel`) para cancelar/quitar/error, azul (`accent`, de `CompanySettings.accent_color`) **solo** para la barra de marca/navegación — nunca en un botón de acción. Definidos como tokens de Tailwind v4 (`@theme` en `index.css`), no clases sueltas repetidas por componente.
- **La marca del tenant se aplica DESPUÉS del login, no antes**: como ya está decidido (§5, login por email sin subdominio propio por cliente), la pantalla de login no puede saber a qué tenant pertenece quien va a entrar — se muestra neutra. `accent_color`/`business_name`/`logo` se cargan y aplican (`applyAccentColor()`, variable CSS `--color-accent`) recién después de un login exitoso, cuando ya se resolvió el tenant vía `UserProfile.company`.
- **Confirmación de venta completada es pantalla completa, no un modal ni un toast** — es lo primero que pedía el brief de diseño (feedback inmediato y grande). El diálogo de confirmación (Radix Dialog) sí se usa, pero solo para "¿cancelar la venta?" (una decisión destructiva chica), no para el resultado de la venta.
- **Redondeo de dinero**: `features/sales/cart.ts` replica en JS el mismo redondeo a centavos que usa `sales.services.create_sale` en el backend (`quantize(Decimal('0.01'))` por línea), para que el total mostrado en pantalla coincida con el que el backend calcula al crear la venta — si no coinciden, `create_sale` rechaza toda la venta (`Los pagos suman X pero la venta totaliza Y`). Límite conocido y documentado en el código: en un caso exacto a medio centavo, Python usa banker's rounding y el `Math.round` de JS no — probabilidad prácticamente nula con precios reales de 2 decimales, no se justificó agregar una librería de precisión decimal (`decimal.js`) para esto en esta sesión.
- **Pago dividido y fiado (CREDIT) quedan fuera de esta pantalla a propósito** — el alcance pedido era "un solo método de pago"; `PaymentPanel` ofrece Efectivo/Tarjeta/Transferencia (con cálculo de cambio para efectivo), no Crédito (que necesitaría selector de cliente, fuera de alcance). Se agrega en una sesión posterior de checkout completo.

### 3.2 Endpoints de apoyo agregados al backend al construir el frontend

Se descubrieron leyendo los serializers/endpoints reales (como pedía la tarea) antes de escribir componentes — ninguno estaba documentado como faltante, pero eran necesarios para que un login real funcionara de punta a punta:

- `GET /api/v1/user-profiles/me/` — perfil del usuario autenticado (branch, role, capabilities) sin tener que adivinar cuál fila del listado (todo el tenant) le corresponde.
- `GET /api/v1/cash-shifts/current/` — el turno abierto del cajero actual, si existe (404 si no) — permite que la app salte la pantalla de apertura si el cajero ya tiene turno (ej. recargó la página) en vez de chocar con "ya tienes un turno abierto".
- `?search=` en `GET /api/v1/products/` (`rest_framework.filters.SearchFilter` sobre `name`/`sku`/`barcode`) — sin esto no había forma de buscar producto, solo listar todo paginado.
- **CORS** (`django-cors-headers`, `CORS_ALLOWED_ORIGINS` en settings, default cubre los puertos de `vite dev`/`vite preview`) — sin esto el navegador bloquea toda llamada del frontend (puerto distinto) a la API.

### 3.3 Tareas programadas — mecanismo elegido: cron del sistema operativo (punto 7, resumen diario de stock bajo)

El backend necesita un correo diario automático (`catalog.send_low_stock_digest`, un management command) que no dispara ningún request HTTP — nadie hace clic para que corra. Se evaluaron tres mecanismos y se decidió **cron del sistema operativo** (crontab en Linux), no Celery Beat ni `django-crontab`:

- **Celery Beat: descartado.** Requiere Celery + un broker (Redis normalmente) corriendo como servicios adicionales. Ninguno de los dos existe en el proyecto hoy (confirmado en `requirements.txt`) — introducirlos solo para un correo diario sería la pieza de infraestructura más pesada del proyecto para el trabajo más liviano. Si en el futuro aparece una necesidad real de tareas asíncronas (ej. generación de PDFs pesada, webhooks con reintentos), se reevalúa entonces — no antes.
- **`django-crontab`: descartado.** Es una dependencia Python nueva (aunque chica) para resolver algo que el cron del sistema operativo ya resuelve gratis en cualquier servidor Linux, incluyendo los servicios de Azure ya decididos en `brief_infraestructura_carlos.md` (App Service Linux vía WebJobs con trigger CRON, o Azure Container Apps Jobs si se migra ahí más adelante). Agregar una librería para envolver algo que el sistema operativo ya hace es la definición de una pieza de infraestructura innecesaria.
- **Cron del sistema operativo: elegido.** Cero dependencias Python nuevas, cero servicios nuevos — coincide con la instrucción explícita de priorizar lo que menos piezas nuevas de infraestructura agregue.

**Comando:** `python manage.py send_low_stock_digest` (`catalog/management/commands/send_low_stock_digest.py`). Recorre cada tenant activo, calcula su stock bajo (`catalog.services.low_stock_products`) y manda un correo a cada `UserProfile` con `role=ADMINISTRADOR` de ese tenant — solo si hay algo que reportar (un tenant sin stock bajo ese día no recibe correo, a propósito: un correo vacío todos los días se aprende a ignorar).

**Qué necesita Carlos en producción:**
- Una entrada de crontab en el servidor (o el WebJob equivalente en Azure App Service) que ejecute el comando una vez al día, por ejemplo a las 8:00 AM hora local:
  ```
  0 8 * * * cd /ruta/al/backend && /ruta/al/venv/bin/python manage.py send_low_stock_digest >> /var/log/pos/low_stock_digest.log 2>&1
  ```
- En Azure App Service (Linux) específicamente: un **WebJob** con trigger CRON apuntando al mismo comando, o (si se migra a Azure Container Apps) un **Container Apps Job** con schedule — ambas opciones evitan tener que administrar un cron manual dentro del contenedor del App Service. Documentado también como bullet operativo en `brief_infraestructura_carlos.md`.
- El mismo SMTP ya configurado para el punto 6 (ticket por correo) — este comando reutiliza las mismas variables de entorno (`EMAIL_HOST`/`EMAIL_HOST_USER`/etc.), no necesita credenciales adicionales.
- En dev/Docker Compose no hay cron corriendo dentro del contenedor — el comando se ejecuta a mano cuando se necesita probar: `docker compose exec backend python manage.py send_low_stock_digest`.

**Limitación real del cálculo de stock bajo, documentada a propósito:** `low_stock_products` solo puede evaluar productos con `requires_batch=True` — son los únicos con una cantidad de stock real medida (`Batch.current_quantity`) en el modelo actual. Un producto con `requires_batch=False` no tiene ningún mecanismo de conteo de existencias hoy, así que no se le puede calcular "stock bajo" contra nada — mismo límite ya documentado para `expired_stock_report`/`near_expiry_stock_report` (§4.3, puntos 1 y 4 de esta sesión). No es un bug: es el estado real del modelo de datos hasta que se decida rastrear stock también para productos sin lote.

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
| business_name | str, blank | **Agregado para el arranque de frontend.** Nombre a mostrar en la interfaz — puede diferir de `Company.name` (nombre legal/de registro). Vacío por default: el frontend cae a un nombre genérico (`Punto de Venta`) si el tenant no lo configuró. |
| logo | ImageField, nullable | Mismo criterio que `catalog.Product.image` (§4.3): prefijo por tenant (`tenant_{id}/branding/...`), Azure Blob vía `django-storages` en producción, storage local en dev, agregado desde el diseño aunque no se use en MVP. |
| accent_color | str (hex, `#RRGGBB`), default `#1E5B94` | Validado con `RegexValidator` — rechaza cualquier cosa que no sea hex de 6 dígitos. **Tono de referencia mantenido tal cual** (azul medio-oscuro, ~4.8:1 de contraste con texto blanco, suficiente para AA) — no se ajustó, ver la nota de la sesión de frontend en §3 sobre dónde se usa. |

**UserProfile** — *cambio importante: login por email, no username*
| Campo | Tipo | Nota |
|---|---|---|
| user | FK a modelo de usuario custom (`AUTH_USER_MODEL`, con `email` como `USERNAME_FIELD`) | Decisión tomada tras encontrar la colisión de username global en la auditoría |
| branch | FK Branch | |
| role | choices: `CAJERO`, `ADMINISTRADOR` | Se quita `DOCTOR`/`RECEPTIONIST` (clínica); Super-admin **no** vive aquí, es `is_staff`/`is_superuser` a nivel Django |
| capabilities | JSONField | incluye `handles_cash` (reutilizado) y **`can_authorize_exceptions`** (nuevo — así se modela Supervisor, no como role aparte) |

**Nota de super-admin/soporte:** agregar `SupportAccessLog` (o extender `AuditLog`) para registrar cuándo un `is_staff` accede a datos de un tenant en modo soporte — gap identificado en la auditoría, pendiente de decidir si entra en MVP o fase 2 (ver sección 7).

**Decisión tomada durante construcción (confirma comportamiento mientras `SupportAccessLog` no existe):** `is_staff`/`is_superuser` **no** es un bypass automático del aislamiento a nivel API. Un usuario staff/superuser sin `UserProfile` ve listas vacías en los endpoints tenant-scoped (no 403, no acceso total); con `UserProfile` queda tan limitado como cualquier usuario normal. La única vía con visibilidad cross-tenant real hoy es Django Admin (`Model.objects.all()` sin filtrar, gateado por `is_staff` a nivel framework) — consistente con la regla de `CLAUDE.md` de que el admin de Django es solo para uso interno de desarrollo. Este comportamiento está fijado por tests (`tenants/tests/test_isolation.py::StaffAndSuperuserAccessTests`) y es el estado correcto hasta que se construya `SupportAccessLog`.

#### 4.1.1 `SupervisorAuthorization` — PIN/reautenticación para `can_authorize_exceptions` (punto 6, construido)

Mecanismo elegido, **preguntado antes de decidir** (no había precedente en el código existente): endpoint separado que devuelve un token corto de un solo uso — no validación inline por operación. Credencial del supervisor: email + password completos, reutilizando `django.contrib.auth.authenticate()` (mismo mecanismo que el login normal), no un PIN corto nuevo — cero piezas de credenciales adicionales que gestionar/resetear.

- `POST /api/v1/auth/authorize-exception/` — `request.user` es el cajero ya autenticado (JWT normal, sin tocar su sesión); el body trae `email`/`password` del supervisor y un `reason` opcional (texto libre — "descuento fuera de política", "cancelación", etc., pos_especificacion_funcional.md §2/§13).
- Autoridad del supervisor: `role == ADMINISTRADOR` **o** `capabilities.can_authorize_exceptions == True` — mismo criterio ya usado en el override de cierre de turno de `CashShift` (§4.2), no una regla nueva.
- **Aislamiento**: el supervisor debe ser del MISMO tenant que quien pide la autorización — un email/password válido de OTRO tenant se rechaza igual que credenciales inválidas (403), sin filtrar si el email existe en otro tenant.
- Token: `secrets.token_urlsafe(32)`, único, vida configurable vía `SUPERVISOR_AUTHORIZATION_TTL_MINUTES` (default 5 min, `.env`). Uso único: `used_at` se marca al consumir, un segundo intento con el mismo token falla. Además del tenant, el token queda atado al cajero específico que lo pidió (`requested_by`) — no es transferible a otra sesión aunque sea del mismo tenant.
- **Todo intento queda en `AuditLog`**, éxito o fallo, con `reason_code` (`invalid_credentials`, `cross_tenant_or_no_profile`, `insufficient_capability`) en los fallos — actor es quien pide en el fallo, el supervisor en el éxito (`supervisor_authorization.granted`/`.denied`/`.consumed`).
- `tenants.services.consume_supervisor_authorization(token, consuming_user)` es el mecanismo genérico de consumo — **ningún endpoint de acción sensible real (cancelar venta, aplicar descuento, devolución) existe todavía**; esta pieza es la infraestructura de autorización que esos endpoints futuros van a llamar, no un feature completo de punta a punta. No se re-valida la capability del supervisor al consumir (solo al emitir) — el token de vida corta ya representa "validado en este momento", mismo modelo de confianza que un access token JWT dentro de su vigencia.
- Vive en `tenants` (no una app nueva): es autenticación de un segundo usuario, mismo dominio que login por email.

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
- PIN/reautenticación para `can_authorize_exceptions`: endpoint separado que valida credenciales del supervisor sin cerrar la sesión del cajero — greenfield, confirmado en la auditoría que no existe nada parecido hoy. ✅ **Construido (punto 6)** — ver detalle completo en §4.1.1.
- `SupportAccessLog` para accesos de super-admin en modo soporte — **decisión pendiente**: ¿entra en MVP o se pospone? Mi recomendación: se puede posponer con seguridad mientras solo tú/Carlos tengan acceso de staff y sea 1 cliente — pero antes de dar acceso de soporte a datos de un tercer/cuarto cliente, ya debería existir.
- **Login alterno por username + fecha de nacimiento (observación de sesión, punto 5) — nota de seguridad explícita, no un descuido.** Es un segundo camino de entrada pensado para el mostrador (rapidez, sin escribir un email completo), NO un reemplazo del login real. Es deliberadamente **más débil** que email+contraseña: la fecha de nacimiento de una persona es adivinable por alguien cercano (familia, compañeros de trabajo) — no tiene la entropía de una contraseña. Se acepta como decisión consciente de conveniencia, con esta mitigación: la cuenta sigue protegida por su contraseña real para cualquier acción que la requiera explícitamente (autorizar una excepción de supervisor, cancelar una venta — ver `tenants.services.request_supervisor_authorization`/`sales.services.cancel_sale`) — el token que este login alterno emite no es "más permisivo" que el normal, es el mismo tipo de token (SimpleJWT), solo llegó por una puerta distinta. `email` sigue siendo `USERNAME_FIELD` y el login principal, sin ningún cambio; `username` es un campo nuevo, corto y opcional, único a nivel sistema (mismo criterio que ya usa `email`, no por tenant — no repite el bug de colisión de pharma_core). Implementado en `tenants.services.request_username_login` / `POST /api/v1/auth/token/username/`.

---

## 8. Testing

- Backend: portar las *reglas* de los tests existentes (`sales/tests.py`, `inventory/tests.py`, `organizations/tests.py`) adaptadas al nuevo modelo — concurrencia en descuento de stock, unicidad de turno abierto, reconciliación de cierre de caja.
- Backend: tests obligatorios para el aislamiento multi-tenant (sección 5) — no es opcional, es la pieza de mayor riesgo de seguridad del sistema.
- Frontend: **el patrón se fijó al construir login/turno/venta (punto 7), no se pospuso** — ver §8.1. Toda feature nueva de frontend lo sigue desde el primer commit, no se agrega después (era el riesgo explícito a evitar: la brecha de testing crece más barata de cerrar mientras la base es chica).

### 8.1 Frontend — patrón de testing (Vitest + React Testing Library + MSW)

Cerrado explícitamente cuando la base todavía era chica (3 pantallas), antes de seguir agregando features — no se dejó para cuando hubiera más superficie que cubrir.

**Stack**: Vitest (mismo motor que Vite, cero config paralela) + `@testing-library/react` (renderiza componentes reales, interactúa por rol/label como lo haría una persona, no por selectores de implementación) + `msw` (Mock Service Worker) para interceptar HTTP. `npm test` corre todo una vez, `npm run test:watch` en modo watch.

**Dónde viven los tests**: co-ubicados junto al archivo que prueban (`Componente.tsx` + `Componente.test.tsx` en la misma carpeta), no en una carpeta `__tests__/` aparte — un test de una feature que se mueve o se borra se mueve/borra junto con su test, no queda huérfano.

```
src/
  test/                      ← infraestructura de testing compartida, NO tests en sí
    setup.ts                   → jest-dom + ciclo de vida de MSW (listen/reset/close) + limpieza de localStorage
    server.ts                    → setupServer(...handlers) de MSW
    handlers.ts                    → camino feliz por default para cada endpoint que el frontend ya consume
    fixtures.ts                      → factories (makeProfile, makeProduct, makeShift...) con la forma EXACTA
                                        de los serializers reales (types/api.ts), no inventada
    test-utils.tsx                     → renderWithAuth() — renderiza una pantalla con un AuthContext ya
                                          resuelto, sin repetir un login real en cada test
  features/
    sales/
      cart.ts
      cart.test.ts               ← junto al archivo que prueba
      SaleScreen.tsx
      SaleScreen.test.tsx
  App.tsx
  App.test.tsx
```

**Cómo se mockea la llamada a la API — decisión explícita, no la única posible**: se evaluaron dos caminos.
1. **Backend real de prueba** (Django test server real contra Postgres) — descartado por "viable rápido": exige orquestar dos procesos/lenguajes distintos solo para correr `npm test`, migraciones, seed de datos, y vuelve a probar la MISMA lógica de negocio que ya tienen los 224 tests de backend (redundante y lento, no es lo que un test de componente de React debería estar validando).
2. **MSW, interceptando la petición HTTP real** (elegido) — los componentes, `services/api/*.ts` y `lib/api-client.ts` corren **sin modificar ni mockear ninguno**; solo se intercepta la respuesta de red al nivel del navegador (vía XHR, que es lo que usa `axios` en jsdom). Esto prueba la integración real componente → servicio → cliente HTTP → parseo de la respuesta, incluyendo casos como el mapeo de errores (ver más abajo), que un mock a nivel de función (`vi.mock('@/services/api/...')`) no ejercitaría de la misma forma.

**Regla explícita — no mockear la lógica de negocio que ya vive en el frontend** (cálculo de IVA, cambio, totales de `features/sales/cart.ts`): los tests dejan correr esa lógica real y confirman el **resultado numérico correcto** (ej. `$47.38` con IVA mixto 16%/0% en el mismo carrito — el mismo caso probado a mano contra el backend real al construir la pantalla), no solo que una función se haya llamado. Mismo estándar que ya se usa en los 224 tests de backend.

**`renderWithAuth()` no es una excepción a esa regla** — no mockea lógica de negocio, aísla una pantalla (`OpenShiftScreen`, `SaleScreen`) de la autenticación (una preocupación aparte) para no repetir un login real en cada test. Para probar el login/la navegación entre pantallas EN SÍ (que es exactamente lo que `AuthProvider`/`App` deciden), se renderiza `<App/>` completo contra MSW, sin este helper — ver `App.test.tsx`.

**El mapeo de errores HTTP → mensaje en español queda fijado por test, no solo corregido una vez**: se encontró un bug real probando el login a mano (SimpleJWT devuelve *"No active account found..."* en inglés sin pasar por `core.exceptions.api_exception_handler`, y se mostraba tal cual). La corrección (`loginErrorMessage()` en `AuthProvider.tsx`, exportada a propósito) tiene tests directos (`AuthProvider.test.tsx`) que fuerzan un 401 con ese texto exacto y confirman que el mensaje mostrado NUNCA es el crudo del backend — más un test de integración en `App.test.tsx` que reproduce el flujo completo vía MSW. Cualquier cambio futuro que rompa el mapeo (ej. alguien reemplaza `loginErrorMessage` por `apiErrorMessage` genérico) lo detecta el test, no un QA manual.

**Nota de entorno, no de la app**: Node 22+ trae un `localStorage` global experimental que choca con el de jsdom en tests (`window.localStorage` queda sin `.clear()`/`.getItem()` funcionales). Se desactiva con `--no-experimental-webstorage` vía `NODE_OPTIONS` en los scripts `test`/`test:watch` de `package.json` (con `cross-env` para que funcione igual en Windows) — nada que ver con el código de la app, es una incompatibilidad puntual de esta versión de Node con jsdom.

### 8.2 Datos de prueba reproducibles (`manage.py seed_demo_data`)

Antes de esta pieza, los datos de prueba de cada sesión de construcción se creaban a mano (shell de Django, browser) y se perdían — no reproducibles, no compartibles con quien levante el proyecto después (Carlos incluido). `core/management/commands/seed_demo_data.py` lo resuelve.

**Por qué vive en `core`** aunque importa modelos de `tenants`/`sales`/`catalog`/`customers`: es una herramienta de desarrollo invocada solo vía `manage.py`, nada la importa en runtime — no aplica la regla de límites entre apps de la sección 2 (esa regla es sobre que la LÓGICA DE NEGOCIO de las apps no se acople entre sí; un script de seed por definición necesita tocar todo el sistema, no es lógica de negocio de ningún dominio en particular).

**Idempotencia — decisión explícita: limpia y recrea, no `get_or_create`.** Se evaluaron las dos:
- `get_or_create` por campo obligaría a mantener dos caminos (crear vs. actualizar-si-cambió) para cada modelo, y un cambio futuro al script podría dejar datos viejos a medio actualizar en un entorno que ya lo había corrido con una versión anterior.
- Limpiar y recrear (elegido) garantiza el mismo resultado exacto sin importar el estado previo — un solo camino de código, sin casos borde de "¿qué pasa si ya existía pero con otro precio?".

El costo (destructivo) es aceptable porque el borrado está **estrictamente acotado**: busca únicamente las 2 companies por su nombre exacto (`Abarrotes La Fortuna`, `Papelería El Estudiante`) y solo toca lo que cuelga de esas dos — nunca borra nada más de la base de datos, confirmado con test manual corriendo el comando con datos reales encima (venta en efectivo, venta a crédito con `CreditMovement` referenciando esa venta, turno abierto) para probar que el orden de limpieza no choca con ningún `on_delete=PROTECT` del modelo de datos, y que un tenant preexistente con nombre distinto (de pruebas manuales previas) queda intacto.

**Qué genera, por tenant**: Company + Branch con nombre/dirección realistas y **distintos entre sí** (no "Tenant A"/"B"), CompanySettings con `business_name`/`accent_color` propios (para que la personalización visual sea visible al cambiar de sesión — ver §4.1), una CashRegister, 3 usuarios (`ADMINISTRADOR`, `CAJERO` con `handles_cash`, y `CAJERO` con `can_authorize_exceptions=True` — el Supervisor del sistema de capabilities, ver §4.1 y decisiones_post_auditoria.md §5), un catálogo de 20+ productos (mezcla de `unit_type`, IVA 0%/16% mixto — alimentos básicos y libros son 0% por ley en México, el resto 16% —, uno con `requires_batch=True` y su `Batch`), y 2-3 `Client` con `CreditAccount` (uno con saldo ya cargado, vía `customers.services.charge_credit`, no escrito directo a la BD). Un tenant además arranca con un `CashShift` ya abierto (`sales.services.open_shift`), para poder entrar directo a la pantalla de venta sin repetir la apertura en cada prueba.

Todas las contraseñas de prueba son `demo1234` (documentada a propósito, no generada al azar — el comando la imprime junto con el correo exacto de cada usuario al terminar, no hay que ir a buscar en la base de datos qué se generó).

---

## 9. Orden de construcción sugerido

1. `core` (TenantScopedQuerySet) + `tenants` (Company/Branch/UserProfile con login por email) — la base de la que depende todo.
2. Extracción de piezas "tal cual" (`audit`, permisos, `CashRegister`/`CashShift`, reportes genéricos, feature flags) como paquete compartido.
3. `catalog` (Product generalizado, con `image` desde el diseño aunque no se use aún).
4. `sales` (Sale/SaleDetail/Payment rediseñados — pago dividido, impuestos reales, `client_uuid`/`occurred_at` en el modelo aunque la cola de sync no se construya todavía).
5. `customers` (fiado) — greenfield. ✅ Construido: `Client`/`CreditAccount`/`CreditMovement`, `Sale.client` conectado, `Payment.method=CREDIT` carga a `CreditAccount` (ver §4.4).
6. Capability `can_authorize_exceptions` + endpoint de PIN — greenfield. ✅ Construido: `tenants.SupervisorAuthorization`, token corto de un solo uso, ver §4.1.1.
7. Frontend: features de venta/caja primero (son el corazón del uso diario), catálogo y clientes después. 🔶 **Arrancado**: login + apertura de turno + venta simple (un solo método de pago) probados de punta a punta contra el backend real — ver §3.1/§3.2. Falta: checkout completo (pago dividido, fiado, descuentos con autorización de supervisor), catálogo, clientes, reportes, admin, vendor.
8. Integración de hardware en tienda real + pruebas con el cliente.
9. (Post-MVP) Cola de sincronización offline completa, `SupportAccessLog`, CFDI.

---

## 10. Pendiente de decisión antes de codificar

- [ ] ¿`variant_attributes` como JSONField es suficiente para papelería en v1, o el cliente ya tiene casos concretos (ej. muchas tallas/colores) que ameriten una tabla de variantes propia desde ahora?
- [ ] Confirmar con Carlos: subdominio propio por cliente vs. login único con selector — afecta cómo se configura DNS/SSL, pendiente del checklist que ya le pasamos.
- [ ] Política de conflicto de stock para cuando se construya la sync offline (venta en negativo + alerta, vs. bloqueo) — sigue siendo decisión de negocio, no técnica.
