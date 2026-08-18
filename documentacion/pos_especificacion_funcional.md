# Especificación Funcional — POS (Abarrotera + Papelería)
### Proyecto derivado de Zenith Pharma | Desarrollado por **ark-dev** | v0.2

---

## 0. Decisión arquitectónica — CONFIRMADO: SaaS multi-tenant

Confirmado: el producto se renta a múltiples clientes, con soporte modular de múltiples sucursales y múltiples cajas por sucursal (un tenant chico puede tener solo 1 sucursal y 1 caja). Esto define:

- Modelo de datos con aislamiento por tenant (a decidir en la auditoría: `tenant_id` en cada tabla con Row-Level Security vs. schema separado por cliente en Postgres — con Django REST lo más común y menos doloroso operativamente es **schema-per-tenant** con `django-tenants`, pero se evalúa contra lo que ya tiene `pharma_core`).
- Onboarding de nuevos clientes (alta de tenant, sucursal(es), caja(s), usuario admin inicial).
- Planes/suscripción y feature flags (ver 0.1).
- Costeo de Azure en dos capas: costo base de la plataforma + costo marginal por tenant/sucursal.

### 0.1 Jerarquía de datos

```
Tenant (cliente que renta el POS)
 └── Sucursal (1 o más)
      └── Caja/Terminal (1 o más por sucursal)
           └── Turnos de caja → Ventas
```

Reportes deben poder verse en 3 niveles: por caja, por sucursal, y consolidado del tenant.

### 0.2 Planes y feature flags (SaaS)

Definir al menos un plan **Básico** (venta, caja, inventario, clientes/fiado, reportes) y un plan **Pro** o addon **CFDI** (facturación fiscal electrónica). El módulo de CFDI debe:
- Vivir desacoplado del flujo de venta (activable/desactivable sin tocar el core de ventas).
- No consumir infraestructura (PAC, timbrado) para tenants que no lo tienen activo.
- Diseñarse desde ahora aunque no se construya en el MVP, para no re-arquitecturar el modelo de venta después.

Falta definir: ¿qué otros módulos serían "premium" a futuro (multi-sucursal como upgrade también, reportes avanzados, etc.)? No es bloqueante para el MVP, pero ayuda a decidir qué se deja como flag desde ya.

---

## 1. Roles y permisos

| Rol | Descripción | Permisos típicos |
|---|---|---|
| **Cajero** | Opera la caja, hace ventas | Vender, cobrar, consultar precios/stock, no puede modificar precios ni eliminar ventas ya cerradas |
| **Supervisor/Encargado** | Turno, autoriza excepciones | Todo lo del cajero + autorizar descuentos, cancelaciones, devoluciones, abrir/cerrar caja de otros usuarios |
| **Administrador/Dueño** | Control total de la tienda | Todo lo anterior + catálogo, precios, proveedores, reportes financieros, usuarios |
| **Super-admin (tú/tu socio)** | Si es SaaS | Gestión de tenants, planes, soporte, no debería ver datos de venta del negocio salvo con fines de soporte |

**Flujo clave:** todo cajero inicia sesión con su propio usuario (no compartir sesión), y cada venta queda asociada a quién la hizo — esto es non-negociable para auditoría y para el corte de caja por cajero.

---

## 2. Flujo de venta (el corazón del sistema)

1. **Apertura de turno/caja** — el cajero declara efectivo inicial (fondo de caja).
2. **Búsqueda de producto** — por escaneo de código de barras, búsqueda por nombre/SKU, o navegación por categoría (para productos sin código, común en papelería a granel o abarrotes sueltos).
3. **Carrito** — agregar/quitar productos, modificar cantidad, productos por peso (granel) vs. por pieza.
4. **Descuentos** — a nivel producto o total, con límites por rol (cajero no puede dar descuento sin autorización de supervisor — requiere PIN/segunda autenticación).
5. **Cobro** — métodos: efectivo, tarjeta, mixto (parte efectivo/parte tarjeta), y **crédito a cliente ("fiado")**, muy común en abarroteras de barrio. Cálculo automático de cambio.
6. **Ticket** — impresión térmica, opción de no imprimir, posible envío digital (WhatsApp/email) si aplica más adelante.
7. **Cancelación de venta** (antes de cerrar) vs. **Devolución** (venta ya cerrada, requiere autorización y genera nota de crédito o reembolso).
8. **Cierre de turno** — corte de caja (ver sección 3).

**Casos especiales del giro:**
- Venta a granel (abarrotes: kilos, gramos, litros) → requiere soporte de báscula o captura manual de peso.
- Productos con variantes (papelería: color, tamaño, ej. "cuaderno profesional 100 hojas cuadrícula").
- Servicios (papelería: fotocopias, impresiones, engargolado) → "producto" tipo servicio, sin control de stock, con precio por unidad (por hoja, por trabajo).
- Recargas telefónicas / pago de servicios (luz, agua) → muy común en abarroteras, considerar si el cliente lo pide desde el inicio o se deja para fase 2.

---

## 3. Caja y turnos

- **Apertura de caja**: monto inicial declarado.
- **Movimientos de caja**: entradas (ej. cambio adicional) y salidas (ej. pago a proveedor de contado, retiro de efectivo) — deben registrarse con motivo y usuario.
- **Corte X**: corte parcial sin cerrar turno (consulta de avance).
- **Corte Z**: cierre definitivo del turno, ya no permite más ventas en esa sesión de caja.
- **Arqueo**: comparación de efectivo esperado (sistema) vs. efectivo contado (físico) → reporta diferencias (sobrante/faltante).
- Reporte de corte debe desglosar por forma de pago (efectivo, tarjeta, crédito) y por cajero.

---

## 4. Inventario y catálogo

- Alta/edición de productos: SKU, código de barras, nombre, categoría, unidad de medida (pieza, kg, litro, paquete), precio de venta, costo, IVA aplicable.
- Variantes (talla/color) si aplica para papelería.
- **Multi-unidad**: vender por pieza o por caja/paquete (ej. vender 1 lápiz o una caja de 12).
- Control de stock en tiempo real, descuenta al vender.
- Alertas de stock bajo / stock mínimo configurable por producto.
- Kardex (historial de movimientos de inventario: entradas, salidas, ajustes, mermas).
- Inventario físico / conteo cíclico con ajuste contra sistema.
- Productos inactivos/descontinuados (no eliminar, solo desactivar, por integridad histórica).

---

## 5. Compras y proveedores

- Catálogo de proveedores.
- Órdenes de compra (opcional en v1, puede ser manual al inicio).
- Recepción de mercancía → actualiza stock y costo.
- Actualización de costo promedio o último costo (define método: PEPS, promedio ponderado, etc.).
- Historial de compras por proveedor.

---

## 6. Clientes y crédito ("fiado")

- Registro de cliente (opcional, no obligatorio para venta de mostrador).
- **Cuentas por cobrar / fiado**: muy relevante en este giro — control de saldo, límite de crédito, abonos, historial de movimientos.
- Reporte de clientes con saldo pendiente.
- (Opcional fase 2) Programa de lealtad / puntos.

---

## 7. Precios, promociones e impuestos

- Precio con/sin IVA, configuración de tasa por producto (no todo lleva la misma tasa, ej. alimentos básicos exentos en México).
- Precios especiales por volumen (mayoreo) si aplica.
- Promociones: 2x1, descuento por cantidad, precio especial por fecha.
- Historial de cambios de precio (auditoría).

---

## 8. Reportes y dashboards

- Ventas por día/semana/mes.
- Ventas por producto/categoría (más vendidos, menos vendidos).
- Ventas por cajero.
- Utilidad bruta (venta - costo).
- Corte de caja histórico.
- Inventario valorizado.
- Clientes con crédito pendiente.
- (Si es SaaS) Dashboard de super-admin: salud de cada tenant, uso, etc.

---

## 9. Multi-sucursal (confirmado: modular)

Un tenant puede tener 1..N sucursales, cada una con 1..N cajas. El cliente actual (abarrotera + papelería) probablemente arranca simple (1 sucursal, 1-2 cajas), pero el sistema debe soportar crecer sin cambios estructurales. Implicaciones:
- Catálogo: definir si es compartido a nivel tenant (recomendado, más simple) o si cada sucursal puede tener su propio subconjunto de precios/stock — **lo más común en retail es catálogo compartido a nivel tenant, con stock independiente por sucursal**.
- Transferencias de inventario entre sucursales (si el cliente llega a tener más de una).
- Reportes consolidados por tenant, y desglosados por sucursal/caja.
- Usuarios pueden estar asignados a una sucursal específica o a todas (rol admin ve todo el tenant).

---

## 10. Hardware / periféricos a soportar

- Lector de código de barras (USB, se comporta como teclado — fácil).
- Impresora térmica de tickets (58mm o 80mm, definir).
- Cajón de dinero (usualmente se abre por comando desde la impresora).
- Báscula (si van a vender a granel) — esto es más complejo, requiere integración específica por marca/protocolo.
- Pantalla secundaria para cliente (opcional, fase 2).

---

## 11. Modo offline / continuidad — Recomendado: resiliencia ligera, no offline-first completo

Decisión recomendada (a confirmar con el equipo): **no** construir un offline-first completo (DB local sincronizada bidireccionalmente, con resolución de conflictos) — es mucho costo de desarrollo para el tamaño de este producto. En su lugar, una **capa de resiliencia**:

- El terminal de venta (`pharma_front`) cachea localmente el catálogo/precios/stock más reciente que recibió.
- Si se pierde la conexión durante una venta, la venta se completa localmente (cálculo de total, cambio, ticket) y se **encola** en el dispositivo.
- Al recuperar conexión, la cola sincroniza automáticamente contra `pharma_core`, con reglas claras de qué pasa si el stock cambió mientras estaba offline (ej. permitir venta en negativo momentáneo y alertar, vs. bloquear — definir con el negocio).
- Límite razonable: pensar la cola para resistir horas de desconexión, no días — si es una caída prolongada, el negocio probablemente vuelve a operar manual de todos modos.

**Por qué ahora y no después:** esto afecta el contrato de la API entre `pharma_front` y `pharma_core` (necesita soportar "venta con timestamp diferido" y conciliación), así que si se decide después de tener el MVP hecho, implica retrabajo real, no solo agregar una feature.

---

## 12. Facturación electrónica (México — CFDI) — Confirmado: addon/upgrade

CFDI **no va en el MVP**, se ofrece como upgrade de plan. Para que esto funcione bien como addon real:
- Integración con un PAC (Proveedor Autorizado de Certificación) — a elegir (ej. Facturama, SW Sapien, Finkok — comparar API/costo por timbre cuando se llegue a esa fase).
- Requiere capturar datos fiscales del cliente final (RFC, uso de CFDI, régimen fiscal) — este dato se pide solo si el tenant tiene el addon activo.
- Cancelaciones fiscales (proceso distinto a una devolución normal de POS).
- El ticket de venta simple (no fiscal) sigue siendo el flujo por default para todos los tenants sin el addon.
- Diseño recomendado: el módulo de venta genera un "documento de venta" interno siempre; el CFDI es una capa que, si está activa, timbra ese documento después. Así el core de ventas nunca depende de si hay o no facturación fiscal.

---

## 13. Seguridad, auditoría y prevención de fraude interno

- Log de acciones sensibles: cancelaciones, devoluciones, descuentos, cambios de precio, apertura/cierre de caja — quién, cuándo, qué.
- Autorización con PIN/segundo factor para acciones sensibles (no solo el login de sesión).
- Prevención de "venta fantasma" (abrir venta y no cobrarla) — reportar tickets abiertos/no cerrados.

---

## 14. Notificaciones/alertas

- Stock bajo.
- Corte de caja con diferencia (faltante/sobrante).
- (Si es SaaS) Vencimiento de renta/suscripción del tenant.

---

## 15. Administración del sistema

- Gestión de usuarios y roles.
- Configuración de la tienda (nombre, dirección, RFC si aplica, moneda, tasas de impuesto).
- (Si es SaaS) Panel de super-admin: alta de tenants, planes, activar/desactivar, ver uso.

---

## 16. Requisitos no funcionales

- **Rendimiento**: la pantalla de venta tiene que responder rápido (búsqueda de producto casi instantánea), es lo más usado del sistema por mucho margen.
- **Disponibilidad**: horario comercial extendido, considerar qué tan crítico es el uptime.
- **Backups**: frecuencia y punto de restauración, especialmente para datos de venta e inventario.
- **Escalabilidad**: si es SaaS, pensar desde ya en cómo crece de 1 a N tenants sin rediseñar.

---

## 17. Reutilización de código desde Zenith Pharma (DRY) — confirmado buen punto de partida

Confirmado por ti: `pharma_core` (Django REST Framework) **ya es multi-tenant**, gran parte de esa capa ya existe — esto es la parte más cara de construir desde cero y ya está resuelta. `pharma_front` es React con tecnologías adicionales (a detallar en la auditoría). Esto cambia el enfoque de la auditoría: ya no es "¿construimos multi-tenancy?", es "¿qué tan limpiamente se puede extraer lo genérico (tenant, auth, roles, venta, caja, catálogo) sin arrastrar acoplamiento a lógica específica de farmacia (lotes, caducidad, recetas, medicamento controlado)?"

Frentes a auditar con Claude Code (ver también sección 18):
- Motor de carrito/venta/cobro → alta probabilidad de reutilización directa.
- Modelo de tenant/sucursal/caja (si ya existe algo similar en Zenith Pharma) → evaluar si mapea a la jerarquía de la sección 0.1 o necesita ajuste.
- Modelo de producto → generalizar (quitar campos específicos de farmacia, agregar variantes/granel/servicios).
- Corte de caja/turnos → probablemente reutilizable casi tal cual.
- Autenticación/roles → reutilizable, confirmar que el modelo de permisos por tenant ya soporta lo de la sección 1.
- Reportes → base reutilizable, ajustar métricas al giro de abarrotera/papelería.

La forma correcta de hacerlo DRY sin ensuciar Zenith Pharma es casi seguro extraer un **paquete/librería interna común** (dominio de "ventas/POS/multi-tenant genérico") del cual tanto Zenith Pharma como este nuevo proyecto (bajo `ark-dev`) consuman, en vez de que el nuevo proyecto importe directo del repo de farmacia.

---

## 18. Lo que falta definir antes de arquitectura y costeo de Azure

**Sobre el negocio/producto:**
- [x] ¿Instalación única o SaaS multi-tenant? → **SaaS multi-tenant, modular en sucursales/cajas**
- [x] ¿Un local o varias ubicaciones? → **Modular, soporta 1..N sucursales**
- [x] ¿CFDI/factura fiscal? → **Addon/upgrade, no en MVP**
- [ ] ¿Necesita modo offline? (sigue abierto — importante decidirlo ahora, no después)
- [ ] ¿Manejan báscula para granel en este cliente en particular?
- [ ] ¿Cuántos clientes futuros estiman rentar el POS en los próximos 12 meses, y a qué ritmo (esto dimensiona el costeo de Azure real, no el de "un solo cliente")?

**Sobre el código existente (pharma_core / pharma_front) — bloquea la auditoría con Claude Code:**
- [ ] Stack real de `pharma_core` (¿Django REST Framework, confirmando tu preferencia habitual?) y `pharma_front` (¿React/Vue/otro?)
- [ ] ¿`pharma_core` ya tiene algo de multi-tenancy, o el POS sería el primer módulo multi-tenant del ecosistema? (si es lo segundo, esto puede justificar extraer el tenant/auth como servicio compartido en vez de solo el módulo de ventas)
- [ ] ¿Dónde vive hoy Zenith Pharma en Azure? ¿Hay recursos ya corriendo que sirvan de línea base de costos, o el POS sería infraestructura nueva desde cero?
- [ ] Volumen estimado por caja (transacciones/día) y usuarios concurrentes esperados, para dimensionar cómputo/DB en Azure sin sobre ni sub-dimensionar.
- [ ] ¿El módulo de ventas de Zenith Pharma ya maneja algo de lo de la sección 2 (carrito, cobro mixto, corte de caja) o se construyó muy amarrado a lógica de farmacia (lotes, caducidad, recetas, medicamento controlado)?

---

## 19. Estimación preliminar de costos en Azure (orden de magnitud)

**Importante:** esto es una estimación de referencia (USD, precios base región US East como línea comparativa), no una cotización. Antes de que Carlos la use para presupuestar, hay que correrla en la [calculadora oficial de Azure](https://azure.microsoft.com/en-us/pricing/calculator/) con la región final — Azure ya tiene región **Mexico Central**, que probablemente conviene por latencia para el Istmo de Tehuantepec, aunque puede variar ligeramente en precio vs. regiones de EE.UU.

### Arquitectura propuesta (mínima viable para SaaS multi-tenant)
- **Backend (Django REST / `pharma_core`)** → Azure App Service (Linux) o Azure Container Apps.
- **Base de datos** → Azure Database for PostgreSQL – Flexible Server, con `tenant_id`/schema por cliente según lo que arroje la auditoría.
- **Frontend (React / `pharma_front`)** → Azure Static Web App o Blob Storage + CDN (muy barato, casi no mueve el presupuesto).
- **Backups** → incluidos en el servicio de PostgreSQL (retención configurable) + snapshots periódicos a Blob Storage.
- **Monitoreo** → Application Insights (tiene capa gratuita generosa para este volumen).

### Tier "MVP" — 1 a 2 clientes (el que ya tienes + margen)
| Servicio | Tamaño de referencia | Costo aprox./mes (USD) |
|---|---|---|
| App Service (backend) | Basic B1 (1 vCPU / 1.75 GB) | ~$13–15 |
| PostgreSQL Flexible Server | Burstable B1ms (1 vCPU / 2 GB) | ~$12–15 |
| Storage BD (32–64 GB) | — | ~$5–8 |
| Frontend (Static Web App / Blob+CDN) | — | ~$0–5 |
| Backups/monitoreo básico | — | ~$0–5 (capa gratuita cubre bastante) |
| **Total estimado** | | **≈ $35–50 USD/mes** |

### Tier "Crecimiento" — 5 clientes (meta a 12 meses)
| Servicio | Tamaño de referencia | Costo aprox./mes (USD) |
|---|---|---|
| App Service (backend) | Basic B2/B3 o Standard S1 | ~$55–75 |
| PostgreSQL Flexible Server | Burstable B2s/B4ms o General Purpose chico | ~$30–60 |
| Storage BD | Escalado con más tenants | ~$10–20 |
| Frontend | — | ~$5–10 |
| Backups/monitoreo | — | ~$5–15 |
| **Total estimado** | | **≈ $100–180 USD/mes** |

**Lectura importante:** a esta escala (1-5 clientes de abarrotera/papelería), el volumen de transacciones diarias de cada tienda **casi no mueve el costo** — un servidor Postgres Burstable maneja sin problema miles de transacciones/día. Lo que sí mueve el presupuesto es el número de tenants y si terminan necesitando alta disponibilidad (réplica) o no. Para este tamaño de negocio, alta disponibilidad probablemente **no se justifica todavía** — mejor invertir en buenos backups y un plan de recuperación rápido ante caída.

**Lo que falta para afinar esto con Carlos:** confirmar región final, si quieren reservar instancias (ahorro con compromiso 1-3 años una vez que el negocio esté validado), y si CFDI (cuando se active como addon) requiere algún costo adicional del PAC que se deba trasladar al cliente.
