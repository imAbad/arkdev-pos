# Brief de Infraestructura — POS ark-dev
### Para: Carlos | De: Emma | 17 ago 2026

---

## 1. Resumen ejecutivo

Vamos a lanzar un POS SaaS multi-tenant (abarrotera/papelería como primer cliente, giro genérico de retail pensado para rentar a más después). **Arrancamos con 1 cliente real, 1 sucursal, 1 caja** — el crecimiento futuro es incierto, así que la infraestructura debe ser barata para empezar pero capaz de escalar sin rediseño. Este documento tiene lo que necesitas para: (a) montar el ambiente de producción del MVP, y (b) saber en qué punto de crecimiento hay que revisar/subir de tier.

**No se necesita sobre-aprovisionar desde el día 1.** Con 1 tenant, el costo de infraestructura es prácticamente irrelevante frente a cualquier otra decisión del negocio — lo importante es dejarlo bien configurado para no tener que migrar de arquitectura después, no para soportar carga que todavía no existe.

---

## 2. Arquitectura ya decidida (contexto técnico)

- **Multi-tenancy**: modelo relacional plano `Tenant → Sucursal → Caja`, aislamiento a nivel API vía un `TenantScopedQuerySet`/mixin centralizado (no `django-tenants`, no schema-per-tenant, no bases separadas por cliente). **Decisión ya tomada y justificada**: a este volumen de clientes, schema-per-tenant no se justifica frente al costo operativo (una migración por schema, routing de conexión, backups por schema).
- **Backend**: Django REST Framework (reutiliza buena parte de `pharma_core` de Zenith Pharma — auditoría de código ya hecha, ver `decisiones_post_auditoria.md` si quieres el detalle completo).
- **Frontend**: React + Vite.
- **Base de datos**: PostgreSQL — **una sola instancia compartida entre todos los tenants** (por el modelo de aislamiento de arriba). Esto es importante para ti: el dimensionamiento de la BD escala con el **número total de tenants**, no con las ventas de un cliente individual.
- **Login**: por email (no username), para evitar colisiones entre tenants desde el diseño.
- **Offline**: capa de resiliencia ligera planeada (cola local + sync), no offline-first completo — no cambia el dimensionamiento de servidor, solo agrega un endpoint de sincronización batch más adelante.

---

## 3. Servicios de Azure necesarios

| Servicio | Para qué |
|---|---|
| **App Service (Linux)** | Backend Django REST |
| **Azure Database for PostgreSQL – Flexible Server** | Base de datos compartida multi-tenant |
| **Azure Static Web App** (o Blob Storage + CDN) | Frontend React |
| **Azure Key Vault** | Secrets (credenciales de BD, JWT signing key, credenciales del PAC cuando se active CFDI) — **no dejar secrets en variables de entorno planas del App Service** |
| **Application Insights** | Monitoreo/logs — capa gratuita cubre este volumen sin problema |
| **Azure Blob Storage** | Backups adicionales / tickets PDF generados |
| **Azure Cost Management + Budgets** | Alertas de presupuesto — ver sección 6, esto es importante para no llevarnos sorpresas |
| **Correo transaccional** (Azure Communication Services Email, SendGrid, o cualquier SMTP) | Ticket de venta por correo y resumen diario de stock bajo — ver nota abajo |

**Correo transaccional — sin proveedor decidido todavía.** El backend ya manda correos reales (ticket de venta a pedido del cajero, resumen diario de stock bajo — ver sección 7 para el mecanismo de ese segundo). En dev, sin credenciales configuradas, cae al backend de consola de Django (el correo se ve en los logs, no se envía de verdad) — funciona sin nada que configurar. En producción SÍ necesita variables de entorno reales: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL` (ver `pos-backend/.env.example`) — estas SÍ deben vivir en Key Vault, no en variables planas del App Service, mismo criterio que el resto de credenciales. Cualquier proveedor SMTP real sirve; no hay decisión tomada sobre cuál todavía, es una de las cosas que necesito que confirmes (ver sección 8).

---

## 4. Configuración recomendada para el arranque (1 cliente real)

**Región: Mexico Central** (por latencia hacia el Istmo de Tehuantepec). Si algún servicio puntual no está disponible ahí todavía, avísame y usamos South Central US como respaldo temporal para ese servicio específico.

| Servicio | Tier de arranque | Costo aprox./mes (USD, referencia) |
|---|---|---|
| App Service | Basic B1 (1 vCPU / 1.75 GB) | ~$13-15 |
| PostgreSQL Flexible Server | Burstable B1ms (1 vCPU / 2 GB) | ~$12-15 |
| Storage BD | 32 GB | ~$5-8 |
| Frontend (Static Web App) | Tier Free | ~$0 |
| Key Vault | — | ~$1-3 (por operaciones, volumen bajo) |
| Application Insights | Capa gratuita | ~$0 |
| Blob Storage (backups extra) | 5-10 GB | ~$1-2 |
| **Total estimado** | | **≈ $35-45 USD/mes** |

**Alta disponibilidad (zone-redundant): NO activarla todavía** — duplica el costo de cómputo de la BD y con 1 cliente el riesgo de downtime no justifica el gasto. Mejor invertir en buenos backups automáticos + un plan de recuperación rápido probado (no solo configurado — probarlo al menos una vez).

---

## 5. Checkpoints de crecimiento — cuándo revisar

No sabemos todavía qué tan rápido va a crecer esto, así que en vez de comprometernos a una curva, aquí están los puntos de decisión concretos por los que hay que pasar **si** crece:

| Señal | Qué revisar | Hacia dónde escalar |
|---|---|---|
| 2do-3er cliente activo | Nada urgente — la config de arranque aguanta varios tenants chicos sin problema | — |
| ~10 tenants activos, o algún cliente reporta lentitud en horas pico | App Service empieza a sentir el tráfico compartido | Subir a Standard S1 + activar autoscale (2 instancias) |
| ~20-25 tenants activos | Postgres Burstable puede quedarse sin CPU credits con tráfico sostenido (no solo picos) | Migrar a General Purpose D2ds_v5 |
| Cualquier momento en que el ritmo de clientes/mes se confirme y sea sostenido por 3+ meses | Vale la pena evaluar instancias reservadas (compromiso 1 año) | Descuento de 30-55% vs. pay-as-you-go, según lo que vimos en Azure — pero no comprometerse antes de tener el ritmo real confirmado |

---

## 6. Alertas de presupuesto (recomendación operativa)

Configura una alerta en **Azure Cost Management + Budgets** en cuanto montes la suscripción — algo como $60 USD/mes de umbral de aviso para esta primera etapa. Así, si algo se dispara por error de configuración (una instancia que no se apagó, un recurso mal dimensionado), nos enteramos por correo antes de que sea un problema en la factura, no después.

---

## 7. Checklist de despliegue inicial

- [ ] Crear resource group dedicado (ej. `arkdev-pos-prod`)
- [ ] Provisionar PostgreSQL Flexible Server (Burstable B1ms, región Mexico Central, backup retention 7 días para empezar)
- [ ] Provisionar App Service (Linux, Basic B1) para `pharma_core`/backend del POS
- [ ] Provisionar Static Web App para el frontend
- [ ] Configurar Key Vault y migrar ahí las credenciales antes de ir a producción (no dejarlas en el código ni en env vars planas)
- [ ] Configurar Application Insights conectado al App Service
- [ ] Configurar alerta de presupuesto (sección 6)
- [ ] Configurar dominio/SSL (definir si es subdominio propio por cliente o un solo dominio con selector de tenant — pendiente de decisión de producto, avísame cuando lo tengamos)
- [ ] Probar restauración de un backup al menos una vez antes de dar de alta al cliente real

---

## 8. Lo que necesito que confirmes o decidas tú

- ¿Mexico Central tiene disponibles todos los servicios de la lista, o hay que ajustar región para alguno en particular?
- ¿Manejamos un solo ambiente de producción por ahora, o vale la pena un ambiente de staging separado desde el inicio (cuesta un poco más, pero evita probar cambios directo en el cliente real)?
- ¿Quién administra el Key Vault y quién tiene acceso a los secrets — tú, yo, ambos?
- ¿Prefieres pay-as-you-go para arrancar (recomendado, dado que no sabemos el ritmo de crecimiento) o ya quieres evaluar algún compromiso desde ahora?
- ¿Qué proveedor de correo transaccional usamos (Azure Communication Services Email, SendGrid, otro)? El backend ya está listo para cualquier SMTP — falta la decisión y las credenciales reales.
