# ark-dev POS

POS SaaS multi-tenant para retail (abarrotería/papelería como primer cliente), derivado por DRY de un sistema existente de farmacia. Documentación completa de producto y arquitectura en [`documentacion/`](documentacion/).

**Antes de tocar código, lee [`CLAUDE.md`](CLAUDE.md)** — define las reglas no negociables del proyecto (multi-tenancy, orden de construcción, convenciones de trabajo).

## Estructura del repo

```
ark-dev/
├── documentacion/     ← especificación funcional, arquitectura técnica, decisiones de auditoría
├── pos-backend/        ← Django REST Framework
│   ├── core/            → TenantScopedQuerySet/mixin, permisos por capability, utils compartidos
│   ├── tenants/          → Company, Branch, CompanySettings, UserProfile (login por email)
│   ├── audit/            → AuditLog
│   ├── sales/             → CashRegister/CashShift, Sale/SaleDetail/Payment
│   ├── catalog/           → Product, Category, Supplier, Batch
│   ├── customers/         → Client, CreditAccount, CreditMovement (fiado)
│   └── config/            → settings, urls
├── pos-frontend/        ← React + Vite + Tailwind — login, apertura de turno y venta simple (ver "Estado actual")
│   └── src/
│       ├── features/       → auth/, shift/, sales/ (por feature, no por tipo de archivo)
│       ├── services/api/    → un cliente por dominio del backend
│       ├── i18n/              → todo el texto visible de la app, centralizado
│       ├── components/ui/      → Radix + Tailwind
│       └── lib/                  → utils sin dependencia de dominio
├── docker-compose.yml
└── CLAUDE.md
```

## Levantar el entorno con Docker

Requiere Docker y Docker Compose.

```bash
cp pos-backend/.env.example pos-backend/.env   # ajusta valores si hace falta, nunca commitees este archivo
docker compose up --build
```

Esto levanta `db` (Postgres 16, con healthcheck y volumen persistente `postgres_data`) y `backend` (Django, puerto `8000`, código montado como volumen — los cambios se reflejan sin rebuild). `backend` espera a que `db` esté healthy antes de arrancar.

Con los contenedores corriendo, en otra terminal:

```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser
```

La API queda en `http://localhost:8000/api/v1/`, el admin de Django (solo para uso interno de desarrollo, ver `CLAUDE.md` regla #4) en `http://localhost:8000/admin/`.

### Sin Docker (venv local)

```bash
cd pos-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # ajusta DB_HOST=localhost y credenciales de tu Postgres local
python manage.py migrate
python manage.py runserver
```

## Levantar el frontend

El frontend no corre dentro de Docker todavía (solo el backend) — se levanta aparte, apuntando al backend en `http://localhost:8000`:

```bash
cd pos-frontend
npm install
npm run dev
```

Vite normalmente usa el puerto `5173` (cae a `5174`/`5175` si ya está ocupado en tu máquina). El backend acepta esos orígenes por CORS de fábrica en dev (`CORS_ALLOWED_ORIGINS` en `config/settings.py`) — si usas otro puerto o dominio, agrégalo ahí o vía variable de entorno.

`pos-frontend/.env` trae `VITE_API_BASE_URL=http://localhost:8000/api/v1` por default.

## Correr los tests

```bash
docker compose exec backend python manage.py test
# o, sin Docker, con el venv activado:
python manage.py test
```

Los tests de aislamiento multi-tenant (uno de los objetivos de mayor riesgo del proyecto, ver `CLAUDE.md` regla #7) y de concurrencia (ej. apertura de turno de caja, `sales/tests/test_cash_shift.py::OpenShiftConcurrencyTests`) corren contra Postgres real, no SQLite — necesitan la base de datos del contenedor `db` o una instancia local.

Frontend (Vitest + React Testing Library + MSW — ver `arquitectura_tecnica_pos.md` §8.1 para el patrón):

```bash
cd pos-frontend
npm test          # una vez
npm run test:watch  # modo watch
```

## Variables de entorno

Ninguna vive commiteada con valores reales (`pos-backend/.env` está en `.gitignore`; `pos-backend/.env.example` trae solo referencia de dev). En producción viven en **Azure Key Vault**, nunca en variables de entorno planas del App Service (`documentacion/brief_infraestructura_carlos.md` §3/§7).

| Variable | Para qué |
|---|---|
| `SECRET_KEY` | Firma criptográfica interna de Django (sesiones, tokens CSRF, etc.) |
| `JWT_SIGNING_KEY` | Firma de los access/refresh tokens (SimpleJWT) — separado de `SECRET_KEY` a propósito, para poder rotar uno sin el otro |
| `DEBUG` | Nunca `True` en producción |
| `ALLOWED_HOSTS` | Hosts permitidos por Django |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | Credenciales de la instancia única de Postgres compartida entre todos los tenants (aislamiento a nivel de aplicación, no schema-per-tenant — ver `arquitectura_tecnica_pos.md` §5) |
| `SUPERVISOR_AUTHORIZATION_TTL_MINUTES` | Vida del token de PIN/reautenticación (default 5 min) |
| `CORS_ALLOWED_ORIGINS` | Orígenes del frontend permitidos por CORS — default cubre los puertos de `vite dev`/`vite preview` en dev |

## Estado actual

Según el orden de construcción de `documentacion/arquitectura_tecnica_pos.md` §9:

- [x] 1. `core` (TenantScopedQuerySet) + `tenants` (Company/Branch/CompanySettings/UserProfile, login por email)
- [x] 2. Extracción "tal cual": `audit`, permisos por capability, `sales.CashRegister`/`CashShift` (apertura/cierre, arqueo ciego)
- [x] 3. `catalog` (Product generalizado, Category, Supplier, Batch)
- [x] 4. `sales.Sale`/`SaleDetail`/`Payment` (pago dividido, impuestos, `client_uuid`/`occurred_at`)
- [x] 5. `customers` (fiado) — `Sale.client` conectado, `Payment.method=CREDIT` carga a `CreditAccount`
- [x] 6. Endpoint de PIN/reautenticación para `can_authorize_exceptions` — `POST /api/v1/auth/authorize-exception/`, token corto de un solo uso (`tenants.SupervisorAuthorization`)
- [~] 7. Frontend (`pos-frontend/`) — arrancado: login + apertura de turno + venta simple (un solo método de pago), probado de punta a punta contra el backend real. Falta: pago dividido, fiado, descuentos con autorización de supervisor, catálogo, clientes, reportes, admin, vendor
- [ ] 8. Integración de hardware en tienda real
- [ ] 9. Cola de sincronización offline, `SupportAccessLog`, CFDI
