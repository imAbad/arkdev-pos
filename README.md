# ark-dev POS

POS SaaS multi-tenant para retail (abarrotería/papelería como primer cliente), derivado por DRY de un sistema existente de farmacia. Documentación completa de producto y arquitectura en [`documentacion/`](documentacion/).

**Antes de tocar código, lee [`CLAUDE.md`](CLAUDE.md)** — define las reglas no negociables del proyecto (multi-tenancy, orden de construcción, convenciones de trabajo).

## Estructura del repo

```
ark-dev/
├── documentacion/     ← especificación funcional, arquitectura técnica, decisiones de auditoría
├── pos-backend/        ← Django REST Framework
│   ├── core/            → TenantScopedQuerySet/mixin, permisos por capability, utils compartidos
│   ├── tenants/          → Company, Branch, CompanySettings, UserProfile (login por email o username)
│   ├── audit/            → AuditLog
│   ├── sales/             → CashRegister/CashShift, Sale/SaleDetail/Payment
│   ├── catalog/           → Product, Category, Supplier, Batch, InventoryAdjustment
│   ├── customers/         → Client, CreditAccount, CreditMovement (fiado)
│   ├── reports/            → ventas, valuación, mermas, cierres de caja, ajustes de inventario (JSON + export .xlsx)
│   └── config/              → settings, urls
├── pos-frontend/        ← React + Vite + Tailwind
│   └── src/
│       ├── features/       → auth/, shift/, sales/, catalog/, reports/, admin/ (por feature, no por tipo de archivo)
│       ├── services/api/    → un cliente por dominio del backend
│       ├── i18n/              → todo el texto visible de la app, centralizado
│       ├── components/ui/      → Radix + Tailwind
│       └── lib/                  → utils sin dependencia de dominio
├── docker-compose.yml
└── CLAUDE.md
```

## Requisitos

- **Docker Desktop** corriendo (para la vía recomendada), o Python 3.13 + Postgres local (para la vía sin Docker).
- **Node.js `^20.19.0` o `>=22.12.0`** para el frontend — es el mínimo real que exige Vite 8 (`pos-frontend/package.json` lo declara en `engines`; hay un `.nvmrc` con `22` para quien use `nvm`). Con un Node más viejo, `npm install`/`npm run dev` fallan o dan errores difíciles de interpretar.

## Backend — levantar con Docker (recomendado)

Requiere Docker y Docker Compose. **No hace falta crear ningún `.env` para este flujo** — `docker-compose.yml` ya trae valores de desarrollo por default para todo lo que Django necesita (`SECRET_KEY`, credenciales de Postgres, etc.), inyectados directo como variables de entorno del contenedor. Un `.env` dentro de `pos-backend/` NO los sobreescribe (las variables de entorno del proceso siempre ganan sobre un archivo `.env` — así funciona `python-decouple`), así que crearlo ahí para este flujo es innecesario y puede confundir.

1. Clona el repo y ubícate en la raíz (`ark-dev/pos`, donde está `docker-compose.yml`).
2. Levanta los contenedores:

   ```bash
   docker compose up --build
   ```

   Esto construye la imagen del backend y levanta `db` (Postgres 16, con healthcheck y volumen persistente `postgres_data`) y `backend` (Django, puerto `8000`, código montado como volumen — los cambios se reflejan sin rebuild). `backend` espera a que `db` esté healthy antes de arrancar. La primera vez tarda unos minutos (build de la imagen + descarga de `postgres:16`); dejar la terminal corriendo.

3. En **otra terminal**, con los contenedores ya corriendo, aplica migraciones y crea un usuario:

   ```bash
   docker compose exec backend python manage.py migrate
   docker compose exec backend python manage.py createsuperuser
   docker compose exec backend python manage.py seed_demo_data   # opcional, ver abajo
   ```

4. Verifica que quedó arriba:
   - API: `http://localhost:8000/api/v1/`
   - Admin de Django (solo uso interno de desarrollo, ver `CLAUDE.md` regla #4): `http://localhost:8000/admin/`

Para apagar: `docker compose down` (los datos de Postgres persisten en el volumen `postgres_data`; para borrarlos también, `docker compose down -v`).

**¿Quieres valores propios en vez de los defaults de dev?** (por ejemplo otra contraseña de Postgres) — crea un archivo `.env` **en la raíz del repo, junto a `docker-compose.yml`** (no dentro de `pos-backend/`), con las variables que quieras sobreescribir (`SECRET_KEY`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DEBUG`, `ALLOWED_HOSTS`). Docker Compose lo lee automáticamente por estar al lado del compose file. Nunca commitees ese archivo.

## Backend — sin Docker (venv local)

A diferencia de Docker, esta vía **sí necesita** un `pos-backend/.env` real — `SECRET_KEY`, `DB_NAME` y `DB_USER` no tienen default en `config/settings.py` y Django no arranca sin ellos.

```bash
cd pos-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edítalo: DB_HOST=localhost y las credenciales de tu Postgres local
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data   # opcional, ver abajo
python manage.py runserver
```

Necesitas una instancia de Postgres corriendo localmente (con una base de datos y usuario que coincidan con lo que pongas en `.env`) — a diferencia del flujo Docker, aquí no hay un contenedor `db` que la levante por ti.

### Datos de prueba (`seed_demo_data`, opcional)

```bash
python manage.py seed_demo_data
```

Genera **2 tenants completos** (`Abarrotes La Fortuna` y `Papelería El Estudiante`) con catálogo (20+ productos cada uno, IVA 0%/16% mixto, uno con lote/caducidad), 3 usuarios por tenant (`ADMINISTRADOR`, `CAJERO`, y un `CAJERO` con `can_authorize_exceptions=True` — el "supervisor" del sistema de capabilities), clientes con fiado (uno ya con saldo pendiente), y un turno de caja abierto en `Abarrotes La Fortuna` para poder entrar directo a vender. Todas las contraseñas son `demo1234` — el comando imprime el correo exacto de cada usuario al terminar.

Es la forma más rápida de confirmar A MANO (no solo con la suite de tests) que un tenant no ve datos de otro: inicia sesión con un usuario de cada tenant y compara.

**Es seguro correrlo varias veces** — limpia y recrea estos 2 tenants por nombre exacto cada vez (no toca ningún otro dato de la base). No usa `get_or_create` a propósito: con datos de prueba, "siempre el mismo resultado exacto sin importar el estado previo" importa más que preservar ediciones manuales que le hayas hecho a estos 2 tenants — si le hiciste cambios a mano y quieres conservarlos, no lo vuelvas a correr.

## Frontend — levantar

El frontend **no corre dentro de Docker** (solo el backend) — se levanta aparte, apuntando al backend en `http://localhost:8000`. El backend (Docker o venv local) debe estar corriendo primero.

```bash
cd pos-frontend
npm install
npm run dev
```

Confirma tu versión de Node antes de `npm install` si algo falla raro:

```bash
node --version   # debe ser ^20.19.0 o >=22.12.0 — ver .nvmrc
```

Vite normalmente usa el puerto `5173` (cae a `5174`/`5175` si ya está ocupado en tu máquina). El backend acepta esos orígenes por CORS de fábrica en dev (`CORS_ALLOWED_ORIGINS` en `config/settings.py`) — si usas otro puerto o dominio, agrégalo ahí o vía variable de entorno.

`pos-frontend/.env` (sí está commiteado — no tiene datos sensibles) trae `VITE_API_BASE_URL=http://localhost:8000/api/v1` por default. Si tu backend corre en otro host/puerto, ajústalo ahí.

## Problemas comunes al levantar el proyecto

- **`docker compose up` falla o no arranca nada**: confirma que Docker Desktop esté abierto y corriendo (no solo instalado) antes de correr el comando.
- **Puerto `8000` o `5432` ya en uso**: si tienes otro Postgres o servicio local usando esos puertos, o bien deténlo, o cambia el mapeo de puertos en `docker-compose.yml` (ej. `"8001:8000"`).
- **`npm install` o `npm run dev` fallan con errores extraños de sintaxis/módulos**: casi siempre es versión de Node vieja — revisa `node --version` contra el requisito de arriba (`^20.19.0` o `>=22.12.0`). Usa `nvm install` (lee `.nvmrc`) si tienes `nvm` instalado.
- **El frontend carga pero las peticiones a la API fallan (CORS o network error)**: confirma que el backend esté corriendo y accesible en `http://localhost:8000` y que `pos-frontend/.env` apunte ahí.
- **`SECRET_KEY` / `DB_NAME` / `DB_USER` — `UndefinedValueError` al correr sin Docker**: falta crear `pos-backend/.env` (ver sección "sin Docker" arriba) — este archivo es obligatorio solo en esa vía, no en Docker.
- **Cambiaste algo en `pos-backend/.env` y no ves el efecto dentro de Docker**: esperado — dentro de `docker compose up`, las variables de entorno del contenedor (definidas en `docker-compose.yml`) tienen prioridad sobre cualquier `.env` dentro de `pos-backend/`. Para sobreescribir valores en Docker, usa un `.env` en la raíz del repo (ver nota al final de la sección de Docker) o edita `docker-compose.yml`.

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

- [x] 1. `core` (TenantScopedQuerySet) + `tenants` (Company/Branch/CompanySettings/UserProfile, login por email o username)
- [x] 2. Extracción "tal cual": `audit`, permisos por capability, `sales.CashRegister`/`CashShift` (apertura/cierre, arqueo ciego)
- [x] 3. `catalog` (Product generalizado, Category, Supplier, Batch, ajustes manuales de stock con motivo obligatorio)
- [x] 4. `sales.Sale`/`SaleDetail`/`Payment` (pago dividido, impuestos, `client_uuid`/`occurred_at`)
- [x] 5. `customers` (fiado) — `Sale.client` conectado, `Payment.method=CREDIT` carga a `CreditAccount`
- [x] 6. Endpoint de PIN/reautenticación para `can_authorize_exceptions` — `POST /api/v1/auth/authorize-exception/`, token corto de un solo uso (`tenants.SupervisorAuthorization`)
- [x] 7. Frontend (`pos-frontend/`) — login, apertura/cierre de turno con arqueo, venta (pago dividido y fiado), catálogo con ajustes de inventario, gestión de clientes con crédito, administración de usuarios, configuración/branding de la empresa (`CompanySettings`), reportes (ventas por producto/categoría/cajero, valuación de inventario, mermas por caducidad, próximos a caducar, cierres de caja con detalle, ajustes de inventario), export a Excel de los reportes principales — probado de punta a punta contra el backend real
- [ ] 8. Integración de hardware en tienda real
- [ ] 9. Cola de sincronización offline, `SupportAccessLog`, CFDI
