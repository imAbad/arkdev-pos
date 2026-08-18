"""Genera datos de prueba reproducibles: 2 tenants completos, para que
cualquiera que levante el proyecto (local o de quien lo levante después,
incluido Carlos) pueda confirmar CON SUS PROPIOS OJOS que un tenant no ve
datos de otro — no solo confiar en la suite de tests.

Vive en `core` a propósito, aunque toca modelos de tenants/sales/catalog/
customers: es una herramienta de desarrollo (invocada solo vía manage.py,
nada la importa en runtime), no lógica de negocio — no aplica la regla de
límites entre apps de arquitectura_tecnica_pos.md §2 (esa regla es sobre
que las APPS no se acoplen en su lógica de negocio entre sí, no sobre un
script de seed que por definición necesita tocar todo el sistema).

Idempotencia: LIMPIA Y RECREA, no get_or_create. Decisión explícita (ver
arquitectura_tecnica_pos.md §8.2): con get_or_create
habría que mantener dos caminos (crear vs. actualizar-si-cambió) por cada
campo de cada modelo, y un cambio futuro en este script podría dejar datos
viejos a medio actualizar en un entorno que ya lo había corrido antes.
Limpiar y recrear garantiza el mismo resultado exacto sin importar el
estado previo — el costo (destructivo) es aceptable porque el borrado
está estrictamente acotado a los 2 tenants que este comando reconoce por
nombre exacto, nunca toca nada más de la base de datos.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from audit.models import AuditLog
from catalog.models import Batch, Category, Product, Supplier
from customers.models import Client, CreditMovement
from customers.services import charge_credit
from sales.models import CashRegister, CashShift, Sale
from sales.services import open_shift
from tenants.models import Branch, Company, CompanySettings, SupervisorAuthorization, User, UserProfile

DEMO_PASSWORD = 'demo1234'

TENANTS = [
    {
        'company_name': 'Abarrotes La Fortuna',
        'branch_name': 'Sucursal Centro',
        'branch_address': 'Calle Morelos 45, Centro',
        'business_name': 'Abarrotes La Fortuna',
        'accent_color': '#C1440E',
        'register_name': 'Caja 1',
        'supplier_name': 'Distribuidora La Central S.A. de C.V.',
        'users': [
            {'local': 'admin', 'label': 'Administradora', 'role': UserProfile.Role.ADMINISTRADOR, 'capabilities': {}},
            {
                'local': 'cajero', 'label': 'Cajero', 'role': UserProfile.Role.CAJERO,
                'capabilities': {'handles_cash': True},
            },
            {
                'local': 'supervisor', 'label': 'Cajero con autorización de excepciones (supervisor)',
                'role': UserProfile.Role.CAJERO,
                'capabilities': {'handles_cash': True, 'can_authorize_exceptions': True},
            },
        ],
        'categories': ['Básicos y despensa', 'Bebidas y botanas', 'Limpieza y cuidado personal'],
        'products': [
            # 0% IVA — alimentos básicos sin procesar (Ley del IVA México)
            {'name': 'Arroz superextra 1kg', 'sku': 'ABR-001', 'category': 0, 'unit_type': 'PIEZA', 'cost': '18.00', 'price': '24.00', 'tax': '0.00'},
            {'name': 'Frijol negro 1kg', 'sku': 'ABR-002', 'category': 0, 'unit_type': 'PIEZA', 'cost': '22.00', 'price': '29.00', 'tax': '0.00'},
            {'name': 'Azúcar estándar 1kg', 'sku': 'ABR-003', 'category': 0, 'unit_type': 'PIEZA', 'cost': '19.00', 'price': '25.00', 'tax': '0.00'},
            {'name': 'Aceite vegetal 1L', 'sku': 'ABR-004', 'category': 0, 'unit_type': 'LITRO', 'cost': '28.00', 'price': '36.00', 'tax': '0.00'},
            {'name': 'Huevo blanco (docena)', 'sku': 'ABR-005', 'category': 0, 'unit_type': 'PIEZA', 'cost': '32.00', 'price': '42.00', 'tax': '0.00'},
            {'name': 'Tortilla de maíz', 'sku': 'ABR-006', 'category': 0, 'unit_type': 'KG', 'cost': '14.00', 'price': '20.00', 'tax': '0.00'},
            {'name': 'Leche entera 1L', 'sku': 'ABR-007', 'category': 0, 'unit_type': 'LITRO', 'cost': '19.00', 'price': '26.50', 'tax': '0.00'},
            {'name': 'Pan blanco de caja', 'sku': 'ABR-008', 'category': 0, 'unit_type': 'PIEZA', 'cost': '24.00', 'price': '32.00', 'tax': '0.00'},
            {'name': 'Sal de mesa 1kg', 'sku': 'ABR-009', 'category': 0, 'unit_type': 'PIEZA', 'cost': '8.00', 'price': '12.00', 'tax': '0.00'},
            {
                'name': 'Yogurt natural 1L', 'sku': 'ABR-010', 'category': 0, 'unit_type': 'LITRO',
                'cost': '26.00', 'price': '34.00', 'tax': '0.00', 'requires_batch': True,
            },
            {'name': 'Chile seco a granel', 'sku': 'ABR-011', 'category': 0, 'unit_type': 'KG', 'cost': '90.00', 'price': '120.00', 'tax': '0.00'},
            # 16% IVA — procesados / no básicos
            {'name': 'Refresco de cola 600ml', 'sku': 'ABR-012', 'category': 1, 'unit_type': 'PIEZA', 'cost': '12.00', 'price': '18.00', 'tax': '16.00'},
            {'name': 'Galletas María', 'sku': 'ABR-013', 'category': 1, 'unit_type': 'PIEZA', 'cost': '14.00', 'price': '19.50', 'tax': '16.00'},
            {'name': 'Papas fritas bolsa', 'sku': 'ABR-014', 'category': 1, 'unit_type': 'PIEZA', 'cost': '15.00', 'price': '21.00', 'tax': '16.00'},
            {'name': 'Cerveza clara six-pack', 'sku': 'ABR-015', 'category': 1, 'unit_type': 'PIEZA', 'cost': '95.00', 'price': '135.00', 'tax': '16.00'},
            {'name': 'Café molido a granel', 'sku': 'ABR-016', 'category': 1, 'unit_type': 'KG', 'cost': '140.00', 'price': '190.00', 'tax': '16.00'},
            {'name': 'Detergente en polvo 1kg', 'sku': 'ABR-017', 'category': 2, 'unit_type': 'PIEZA', 'cost': '28.00', 'price': '39.00', 'tax': '16.00'},
            {'name': 'Jabón de tocador', 'sku': 'ABR-018', 'category': 2, 'unit_type': 'PIEZA', 'cost': '9.00', 'price': '14.00', 'tax': '16.00'},
            {'name': 'Papel higiénico (4 rollos)', 'sku': 'ABR-019', 'category': 2, 'unit_type': 'PAQUETE', 'cost': '32.00', 'price': '45.00', 'tax': '16.00'},
            {'name': 'Recarga telefónica $50', 'sku': 'ABR-020', 'category': 1, 'unit_type': 'SERVICIO', 'cost': '48.50', 'price': '50.00', 'tax': '16.00'},
        ],
        'clients': [
            {'name': 'Sra. Guadalupe Martínez', 'phone': '271-100-2233', 'credit_limit': '500.00', 'initial_charge': '150.00'},
            {'name': 'Don Ramiro Torres', 'phone': '271-100-4455', 'credit_limit': '1000.00', 'initial_charge': '0.00'},
            {'name': 'Familia Hernández', 'phone': '271-100-6677', 'credit_limit': '300.00', 'initial_charge': '0.00'},
        ],
        'open_shift': True,
    },
    {
        'company_name': 'Papelería El Estudiante',
        'branch_name': 'Sucursal Plaza',
        'branch_address': 'Av. Juárez 210, Plaza Comercial',
        'business_name': 'Papelería El Estudiante',
        'accent_color': '#3B4C9E',
        'register_name': 'Caja 1',
        'supplier_name': 'Papelera del Sureste S.A. de C.V.',
        'users': [
            {'local': 'admin', 'label': 'Administrador', 'role': UserProfile.Role.ADMINISTRADOR, 'capabilities': {}},
            {
                'local': 'cajero', 'label': 'Cajera', 'role': UserProfile.Role.CAJERO,
                'capabilities': {'handles_cash': True},
            },
            {
                'local': 'supervisor', 'label': 'Cajero con autorización de excepciones (supervisor)',
                'role': UserProfile.Role.CAJERO,
                'capabilities': {'handles_cash': True, 'can_authorize_exceptions': True},
            },
        ],
        'categories': ['Libros', 'Escritura y oficina', 'Manualidades y servicios'],
        'products': [
            # 0% IVA — libros (Ley del IVA México)
            {'name': 'Libro de cuentos infantil', 'sku': 'PAP-001', 'category': 0, 'unit_type': 'PIEZA', 'cost': '55.00', 'price': '89.00', 'tax': '0.00'},
            {'name': 'Diccionario escolar', 'sku': 'PAP-002', 'category': 0, 'unit_type': 'PIEZA', 'cost': '70.00', 'price': '110.00', 'tax': '0.00'},
            # 16% IVA — el resto de la papelería
            {'name': 'Cuaderno profesional cuadrícula', 'sku': 'PAP-003', 'category': 1, 'unit_type': 'PIEZA', 'cost': '18.00', 'price': '28.00', 'tax': '16.00'},
            {'name': 'Cuaderno profesional raya', 'sku': 'PAP-004', 'category': 1, 'unit_type': 'PIEZA', 'cost': '18.00', 'price': '28.00', 'tax': '16.00'},
            {'name': 'Lápiz del número 2', 'sku': 'PAP-005', 'category': 1, 'unit_type': 'PIEZA', 'cost': '2.50', 'price': '5.00', 'tax': '16.00'},
            {'name': 'Bolígrafo tinta azul', 'sku': 'PAP-006', 'category': 1, 'unit_type': 'PIEZA', 'cost': '3.00', 'price': '6.00', 'tax': '16.00'},
            {'name': 'Bolígrafo tinta negra', 'sku': 'PAP-007', 'category': 1, 'unit_type': 'PIEZA', 'cost': '3.00', 'price': '6.00', 'tax': '16.00'},
            {'name': 'Marcador para pizarrón blanco', 'sku': 'PAP-008', 'category': 1, 'unit_type': 'PIEZA', 'cost': '9.00', 'price': '15.00', 'tax': '16.00'},
            {'name': 'Goma de borrar', 'sku': 'PAP-009', 'category': 1, 'unit_type': 'PIEZA', 'cost': '3.50', 'price': '7.00', 'tax': '16.00'},
            {'name': 'Sacapuntas metálico', 'sku': 'PAP-010', 'category': 1, 'unit_type': 'PIEZA', 'cost': '4.00', 'price': '8.00', 'tax': '16.00'},
            {'name': 'Regla de plástico 30cm', 'sku': 'PAP-011', 'category': 1, 'unit_type': 'PIEZA', 'cost': '5.00', 'price': '10.00', 'tax': '16.00'},
            {'name': 'Corrector líquido', 'sku': 'PAP-012', 'category': 1, 'unit_type': 'PIEZA', 'cost': '10.00', 'price': '18.00', 'tax': '16.00'},
            {
                'name': 'Resistol blanco 250ml', 'sku': 'PAP-013', 'category': 1, 'unit_type': 'PIEZA',
                'cost': '12.00', 'price': '20.00', 'tax': '16.00', 'requires_batch': True,
            },
            {'name': 'Folder tamaño carta', 'sku': 'PAP-014', 'category': 1, 'unit_type': 'PIEZA', 'cost': '2.00', 'price': '4.00', 'tax': '16.00'},
            {'name': 'Hojas blancas tamaño carta (paquete)', 'sku': 'PAP-015', 'category': 1, 'unit_type': 'PAQUETE', 'cost': '65.00', 'price': '95.00', 'tax': '16.00'},
            {'name': 'Mochila escolar', 'sku': 'PAP-016', 'category': 2, 'unit_type': 'PIEZA', 'cost': '180.00', 'price': '299.00', 'tax': '16.00'},
            {'name': 'Colores de madera (caja c/12)', 'sku': 'PAP-017', 'category': 2, 'unit_type': 'PIEZA', 'cost': '25.00', 'price': '42.00', 'tax': '16.00'},
            {'name': 'Confeti de colores a granel', 'sku': 'PAP-018', 'category': 2, 'unit_type': 'KG', 'cost': '80.00', 'price': '130.00', 'tax': '16.00'},
            {'name': 'Pegamento blanco a granel', 'sku': 'PAP-019', 'category': 2, 'unit_type': 'LITRO', 'cost': '45.00', 'price': '70.00', 'tax': '16.00'},
            {'name': 'Fotocopias', 'sku': 'PAP-020', 'category': 2, 'unit_type': 'SERVICIO', 'cost': '0.30', 'price': '1.00', 'tax': '16.00'},
            {'name': 'Engargolado', 'sku': 'PAP-021', 'category': 2, 'unit_type': 'SERVICIO', 'cost': '8.00', 'price': '20.00', 'tax': '16.00'},
        ],
        'clients': [
            {'name': 'Escuela Primaria Benito Juárez', 'phone': '271-200-1122', 'credit_limit': '2000.00', 'initial_charge': '450.00'},
            {'name': 'Prof. Alicia Reyes', 'phone': '271-200-3344', 'credit_limit': '500.00', 'initial_charge': '0.00'},
            {'name': 'Carlos Jiménez (estudiante)', 'phone': '271-200-5566', 'credit_limit': '200.00', 'initial_charge': '0.00'},
        ],
        'open_shift': False,
    },
]


class Command(BaseCommand):
    help = (
        'Genera 2 tenants completos con datos de prueba reproducibles '
        '(catálogo, usuarios de los 3 niveles, clientes con fiado) para '
        'probar aislamiento multi-tenant y personalización visual a mano. '
        'Limpia y recrea si ya existen — seguro de correr varias veces.'
    )

    def handle(self, *args, **options):
        summaries = []
        with transaction.atomic():
            for spec in TENANTS:
                self._wipe_tenant(spec['company_name'])
            for spec in TENANTS:
                summaries.append(self._build_tenant(spec))
        self._print_summary(summaries)

    # -- limpieza -----------------------------------------------------

    def _wipe_tenant(self, company_name):
        try:
            company = Company.objects.get(name=company_name)
        except Company.DoesNotExist:
            return

        # Orden estricto para no chocar con FKs on_delete=PROTECT — ver
        # el docstring del módulo y la nota en arquitectura_tecnica_pos.md.
        CreditMovement.objects.filter(company=company).delete()
        Sale.objects.filter(company=company).delete()  # cascada: SaleDetail, Payment
        SupervisorAuthorization.objects.filter(company=company).delete()
        CashShift.objects.filter(company=company).delete()
        Batch.objects.filter(company=company).delete()
        Product.objects.filter(company=company).delete()
        AuditLog.objects.filter(company=company).delete()

        user_ids = list(UserProfile.objects.filter(company=company).values_list('user_id', flat=True))
        # Cascada del resto: Branch, CompanySettings, UserProfile,
        # CashRegister, Category, Supplier, Client, CreditAccount.
        company.delete()
        User.objects.filter(id__in=user_ids).delete()

        self.stdout.write(f'  (limpiado: {company_name} ya existía)')

    # -- construcción ---------------------------------------------------

    def _build_tenant(self, spec):
        company = Company.objects.create(name=spec['company_name'])
        branch = Branch.objects.create(company=company, name=spec['branch_name'], address=spec['branch_address'])
        CompanySettings.objects.create(
            company=company,
            business_name=spec['business_name'],
            accent_color=spec['accent_color'],
        )
        register = CashRegister.objects.create(branch=branch, name=spec['register_name'])

        users = []
        for user_spec in spec['users']:
            email = f"{user_spec['local']}@{self._domain(spec['company_name'])}"
            user = User.objects.create_user(email=email, password=DEMO_PASSWORD)
            UserProfile.objects.create(
                user=user, branch=branch, role=user_spec['role'], capabilities=user_spec['capabilities'],
            )
            users.append({'email': email, 'label': user_spec['label'], 'role': user_spec['role']})

        categories = [Category.objects.create(company=company, name=name) for name in spec['categories']]
        supplier = Supplier.objects.create(company=company, name=spec['supplier_name'])

        for product_spec in spec['products']:
            product = Product.objects.create(
                company=company,
                name=product_spec['name'],
                sku=product_spec['sku'],
                category=categories[product_spec['category']],
                supplier=supplier,
                unit_type=product_spec['unit_type'],
                requires_batch=product_spec.get('requires_batch', False),
                cost_price=Decimal(product_spec['cost']),
                sale_price=Decimal(product_spec['price']),
                tax_rate=Decimal(product_spec['tax']),
                min_stock=5,
            )
            if product_spec.get('requires_batch'):
                Batch.objects.create(
                    product=product,
                    branch=branch,
                    batch_number='LOTE-0001',
                    initial_quantity=50,
                    expiration_date=timezone.localdate() + timedelta(days=180),
                )

        for client_spec in spec['clients']:
            client = Client.objects.create(
                company=company,
                name=client_spec['name'],
                phone=client_spec['phone'],
                credit_limit=Decimal(client_spec['credit_limit']),
            )
            initial_charge = Decimal(client_spec['initial_charge'])
            if initial_charge > 0:
                charge_credit(account=client.credit_account, amount=initial_charge)

        shift = None
        if spec['open_shift']:
            cajero_user = User.objects.get(email=f"cajero@{self._domain(spec['company_name'])}")
            shift = open_shift(user=cajero_user, cash_register=register, opening_balance=Decimal('1000.00'))

        return {
            'company_name': spec['company_name'],
            'business_name': spec['business_name'],
            'accent_color': spec['accent_color'],
            'users': users,
            'product_count': len(spec['products']),
            'client_count': len(spec['clients']),
            'shift_opened': shift is not None,
        }

    @staticmethod
    def _domain(company_name):
        # "Abarrotes La Fortuna" -> "fortuna.test" (última palabra del
        # nombre, solo para armar correos de prueba legibles — no es un
        # dominio real).
        slug = ''.join(ch for ch in company_name.split()[-1].lower() if ch.isalnum())
        return f'{slug}.test'

    # -- resumen en consola ---------------------------------------------

    def _print_summary(self, summaries):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Datos de prueba generados — 2 tenants listos.'))
        self.stdout.write(f'Password de TODOS los usuarios de prueba: {DEMO_PASSWORD}')
        self.stdout.write('')

        for summary in summaries:
            self.stdout.write(self.style.MIGRATE_HEADING(summary['company_name']))
            self.stdout.write(f"  business_name: {summary['business_name']}  ·  accent_color: {summary['accent_color']}")
            self.stdout.write(f"  Catálogo: {summary['product_count']} productos  ·  Clientes con fiado: {summary['client_count']}")
            if summary['shift_opened']:
                self.stdout.write('  Turno de caja: ABIERTO (fondo inicial $1,000.00) — se puede entrar directo a vender.')
            self.stdout.write('  Usuarios:')
            for user in summary['users']:
                self.stdout.write(f"    - {user['email']}  ({user['label']})")
            self.stdout.write('')

        self.stdout.write('Confirma el aislamiento entre tenants: inicia sesión con un usuario de cada')
        self.stdout.write('tenant (en pestañas o navegadores distintos) y verifica que ninguno ve el')
        self.stdout.write('catálogo, clientes ni personalización visual (color/nombre) del otro.')
