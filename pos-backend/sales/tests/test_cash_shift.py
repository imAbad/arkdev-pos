"""CashRegister/CashShift: apertura, cierre con arqueo ciego, y los mismos
dos estándares que el resto del proyecto — aislamiento multi-tenant y
permisos negados, no solo el happy path (ver CLAUDE.md #7 y
arquitectura_tecnica_pos.md §8)."""
import threading
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from catalog.tests.factories import create_product
from customers.tests.factories import create_client
from sales.models import CashRegister, CashShift
from sales.services import RegisterAlreadyOpenError, ShiftError, ShiftPermissionError, close_shift, open_shift
from sales.tests.factories import create_cash_register, make_sale
from tenants.models import User, UserProfile
from tenants.tests.factories import create_branch, create_full_tenant, create_user_with_profile


class CashShiftUniqueOpenPerRegisterTests(TestCase):
    """La garantía real contra la condición de carrera: el UniqueConstraint
    parcial en CashShift.Meta, no un chequeo previo en Python."""

    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test',
            capabilities={'handles_cash': True},
        )
        self.register = create_cash_register(self.tenant['branch'])

    def test_constraint_blocks_second_open_shift_same_register(self):
        CashShift.objects.create(
            cash_register=self.register, user=self.tenant['user'], opening_balance=Decimal('100'),
        )
        other_user, _ = create_user_with_profile(
            'cajero2@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CashShift.objects.create(
                    cash_register=self.register, user=other_user, opening_balance=Decimal('50'),
                )

    def test_closed_shift_does_not_block_reopening_same_register(self):
        shift = CashShift.objects.create(
            cash_register=self.register, user=self.tenant['user'], opening_balance=Decimal('100'),
        )
        shift.status = CashShift.Status.CLOSED
        shift.closed_by = self.tenant['user']
        shift.save()

        CashShift.objects.create(
            cash_register=self.register, user=self.tenant['user'], opening_balance=Decimal('50'),
        )
        self.assertEqual(
            CashShift.objects.filter(cash_register=self.register, status=CashShift.Status.OPEN).count(), 1,
        )


class OpenShiftServiceTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test',
            capabilities={'handles_cash': True},
        )
        self.register = create_cash_register(self.tenant['branch'])

    def test_open_shift_creates_open_shift_with_opening_balance(self):
        shift = open_shift(user=self.tenant['user'], cash_register=self.register, opening_balance=Decimal('200'))
        self.assertEqual(shift.status, CashShift.Status.OPEN)
        self.assertEqual(shift.opening_balance, Decimal('200'))
        self.assertEqual(shift.company_id, self.tenant['company'].id)

    def test_cannot_open_shift_if_already_has_open_shift(self):
        open_shift(user=self.tenant['user'], cash_register=self.register)
        other_register = create_cash_register(self.tenant['branch'], name='Caja 2')
        with self.assertRaises(ShiftError):
            open_shift(user=self.tenant['user'], cash_register=other_register)

    def test_cannot_open_shift_on_register_from_another_branch(self):
        other_branch = create_branch(self.tenant['company'], name='Sucursal Sur')
        other_register = create_cash_register(other_branch)
        with self.assertRaises(ShiftError):
            open_shift(user=self.tenant['user'], cash_register=other_register)

    def test_cannot_open_inactive_register(self):
        self.register.is_active = False
        self.register.save()
        with self.assertRaises(ShiftError):
            open_shift(user=self.tenant['user'], cash_register=self.register)

    def test_second_open_on_already_open_register_raises_register_already_open_error(self):
        # Otro usuario (sin turno propio abierto) intenta abrir turno en una
        # caja que YA tiene turno abierto de alguien más — se distingue de
        # un ShiftError genérico (subclase específica) para que el
        # frontend pueda ofrecer continuar/cerrar/vender en el existente
        # en vez de solo mostrar el mensaje (punto 0).
        open_shift(user=self.tenant['user'], cash_register=self.register)
        other_user, _ = create_user_with_profile(
            'cajero2@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )
        with self.assertRaises(RegisterAlreadyOpenError):
            open_shift(user=other_user, cash_register=self.register)


class OpenShiftConcurrencyTests(TransactionTestCase):
    """Dos requests reales y simultáneas sobre la misma caja: exactamente
    una debe ganar. Mismo patrón que las pruebas de concurrencia FEFO de
    pharma_core (hilos reales, no una simulación serial)."""

    def test_concurrent_open_shift_requests_only_one_succeeds(self):
        tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'cajero1@donchuy.test',
            capabilities={'handles_cash': True},
        )
        user2, _ = create_user_with_profile(
            'cajero2@donchuy.test', tenant['branch'], capabilities={'handles_cash': True},
        )
        register = create_cash_register(tenant['branch'])

        results = []

        def attempt(user):
            try:
                open_shift(user=user, cash_register=register)
                results.append('OPENED')
            except ShiftError:
                results.append('REJECTED')
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt, args=(tenant['user'],))
        t2 = threading.Thread(target=attempt, args=(user2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(results), ['OPENED', 'REJECTED'])
        self.assertEqual(
            CashShift.objects.filter(cash_register=register, status=CashShift.Status.OPEN).count(), 1,
        )


class CloseShiftServiceTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test',
            capabilities={'handles_cash': True},
        )
        self.register = create_cash_register(self.tenant['branch'])
        self.shift = open_shift(user=self.tenant['user'], cash_register=self.register, opening_balance=Decimal('100'))

    def test_owner_can_close_own_shift(self):
        closed = close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('100'))
        self.assertEqual(closed.status, CashShift.Status.CLOSED)
        self.assertEqual(closed.closed_by, self.tenant['user'])
        self.assertIsNotNone(closed.closed_at)

    def test_expected_closing_balance_with_no_sales_is_just_the_opening_balance(self):
        closed = close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('130'))
        self.assertEqual(closed.expected_closing_balance, Decimal('100'))
        self.assertEqual(closed.expected_voucher_total, Decimal('0'))

    def test_expected_closing_balance_sums_cash_sales_of_the_shift(self):
        product = create_product(self.tenant['company'], tax_rate=Decimal('0'))
        make_sale(self.shift, product, quantity=Decimal('1'), unit_price=Decimal('50'), payment_method='CASH')
        make_sale(self.shift, product, quantity=Decimal('1'), unit_price=Decimal('30'), payment_method='CASH')

        closed = close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('180'))
        # 100 de apertura + 50 + 30 de ventas en efectivo del turno
        self.assertEqual(closed.expected_closing_balance, Decimal('180'))

    def test_expected_voucher_total_sums_card_and_transfer_but_not_cash(self):
        product = create_product(self.tenant['company'], tax_rate=Decimal('0'))
        make_sale(self.shift, product, quantity=Decimal('1'), unit_price=Decimal('50'), payment_method='CASH')
        make_sale(self.shift, product, quantity=Decimal('1'), unit_price=Decimal('25'), payment_method='CARD')
        make_sale(self.shift, product, quantity=Decimal('1'), unit_price=Decimal('15'), payment_method='TRANSFER')

        closed = close_shift(
            shift=self.shift, closing_user=self.tenant['user'],
            actual_closing_balance=Decimal('150'), actual_voucher_total=Decimal('40'),
        )
        self.assertEqual(closed.expected_closing_balance, Decimal('150'))  # 100 + 50 cash
        self.assertEqual(closed.expected_voucher_total, Decimal('40'))    # 25 card + 15 transfer

    def test_credit_sales_count_in_neither_cash_nor_voucher_expected(self):
        # Fiado no mueve dinero en la caja al momento de la venta.
        product = create_product(self.tenant['company'], tax_rate=Decimal('0'))
        client = create_client(self.tenant['company'])
        make_sale(
            self.shift, product, quantity=Decimal('1'), unit_price=Decimal('99'),
            payment_method='CREDIT', client=client,
        )

        closed = close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('100'))
        self.assertEqual(closed.expected_closing_balance, Decimal('100'))  # solo apertura
        self.assertEqual(closed.expected_voucher_total, Decimal('0'))

    def test_cash_and_voucher_difference_are_computed_from_declared_vs_expected(self):
        closed = close_shift(
            shift=self.shift,
            closing_user=self.tenant['user'],
            actual_closing_balance=Decimal('130'),
            actual_voucher_total=Decimal('20'),
        )
        self.assertEqual(closed.cash_difference, Decimal('30'))
        self.assertEqual(closed.voucher_difference, Decimal('20'))

    def test_cannot_close_already_closed_shift(self):
        close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('100'))
        with self.assertRaises(ShiftError):
            close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('100'))

    def test_plain_cajero_cannot_close_others_shift(self):
        other_cajero, _ = create_user_with_profile(
            'otro@donchuy.test', self.tenant['branch'], capabilities={'handles_cash': True},
        )
        with self.assertRaises(ShiftPermissionError):
            close_shift(shift=self.shift, closing_user=other_cajero, actual_closing_balance=Decimal('100'))

    def test_administrador_can_close_others_shift_and_it_is_audited(self):
        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant['branch'],
            role=UserProfile.Role.ADMINISTRADOR, capabilities={'handles_cash': True},
        )
        closed = close_shift(shift=self.shift, closing_user=admin, actual_closing_balance=Decimal('100'))
        self.assertEqual(closed.closed_by, admin)

        entry = AuditLog.objects.get(company=self.tenant['company'], action='cash_shift.closed_by_override')
        self.assertEqual(entry.changes['via'], 'ADMINISTRADOR')
        self.assertEqual(entry.changes['owner'], self.tenant['user'].email)
        self.assertEqual(entry.changes['closed_by'], admin.email)

    def test_cajero_with_can_authorize_exceptions_can_close_others_shift_and_it_is_audited(self):
        # Supervisor = CAJERO + capability, no un role aparte (ver
        # decisiones_post_auditoria.md §5).
        supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.tenant['branch'],
            role=UserProfile.Role.CAJERO,
            capabilities={'handles_cash': True, 'can_authorize_exceptions': True},
        )
        closed = close_shift(shift=self.shift, closing_user=supervisor, actual_closing_balance=Decimal('100'))
        self.assertEqual(closed.closed_by, supervisor)

        entry = AuditLog.objects.get(company=self.tenant['company'], action='cash_shift.closed_by_override')
        self.assertEqual(entry.changes['via'], 'can_authorize_exceptions')

    def test_owner_closing_own_shift_does_not_create_override_audit_log(self):
        close_shift(shift=self.shift, closing_user=self.tenant['user'], actual_closing_balance=Decimal('100'))
        self.assertFalse(AuditLog.objects.filter(action='cash_shift.closed_by_override').exists())


class CashShiftApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'cajero@donchuy.test',
            capabilities={'handles_cash': True},
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'cajero@estrella.test',
            capabilities={'handles_cash': True},
        )
        self.register_a = create_cash_register(self.tenant_a['branch'])
        self.register_b = create_cash_register(self.tenant_b['branch'])

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_open_shift_via_api(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/cash-shifts/open-shift/',
            {'cash_register_id': self.register_a.id, 'opening_balance': '150.00'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'OPEN')

    def test_open_shift_rejects_cash_register_from_other_tenant(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/cash-shifts/open-shift/',
            {'cash_register_id': self.register_b.id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(CashShift.objects.filter(cash_register=self.register_b).exists())

    def test_close_shift_via_api(self):
        self._auth(self.tenant_a['user'])
        open_response = self.client.post(
            '/api/v1/cash-shifts/open-shift/',
            {'cash_register_id': self.register_a.id, 'opening_balance': '100.00'},
            format='json',
        )
        shift_id = open_response.data['id']

        close_response = self.client.post(
            f'/api/v1/cash-shifts/{shift_id}/close-shift/',
            {'actual_closing_balance': '100.00'},
            format='json',
        )
        self.assertEqual(close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(close_response.data['status'], 'CLOSED')
        self.assertEqual(close_response.data['cash_difference'], '0.00')

    def test_cannot_retrieve_other_tenant_shift(self):
        self._auth(self.tenant_a['user'])
        open_res = self.client.post(
            '/api/v1/cash-shifts/open-shift/', {'cash_register_id': self.register_a.id}, format='json',
        )
        shift_a_id = open_res.data['id']

        self._auth(self.tenant_b['user'])
        response = self.client.get(f'/api/v1/cash-shifts/{shift_a_id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_close_other_tenant_shift_via_api(self):
        self._auth(self.tenant_a['user'])
        open_res = self.client.post(
            '/api/v1/cash-shifts/open-shift/', {'cash_register_id': self.register_a.id}, format='json',
        )
        shift_a_id = open_res.data['id']

        self._auth(self.tenant_b['user'])
        response = self.client.post(
            f'/api/v1/cash-shifts/{shift_a_id}/close-shift/', {'actual_closing_balance': '0'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.tenant_a_shift = CashShift.objects.get(id=shift_a_id)
        self.assertEqual(self.tenant_a_shift.status, CashShift.Status.OPEN)

    def test_open_shift_on_already_open_register_returns_409_with_machine_readable_code(self):
        self._auth(self.tenant_a['user'])
        self.client.post('/api/v1/cash-shifts/open-shift/', {'cash_register_id': self.register_a.id}, format='json')

        other_user, _ = create_user_with_profile(
            'otro@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        self._auth(other_user)
        response = self.client.post(
            '/api/v1/cash-shifts/open-shift/', {'cash_register_id': self.register_a.id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data['code'], 'register_already_open')

    def test_for_register_returns_the_open_shift_of_any_user_same_tenant(self):
        self._auth(self.tenant_a['user'])
        open_res = self.client.post(
            '/api/v1/cash-shifts/open-shift/', {'cash_register_id': self.register_a.id}, format='json',
        )
        shift_id = open_res.data['id']

        other_user, _ = create_user_with_profile(
            'otro@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        self._auth(other_user)
        response = self.client.get(
            '/api/v1/cash-shifts/for-register/', {'cash_register_id': self.register_a.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], shift_id)
        self.assertEqual(response.data['user_email'], self.tenant_a['user'].email)

    def test_for_register_404_when_register_has_no_open_shift(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get(
            '/api/v1/cash-shifts/for-register/', {'cash_register_id': self.register_a.id},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_for_register_does_not_leak_other_tenant_shift(self):
        self._auth(self.tenant_b['user'])
        self.client.post('/api/v1/cash-shifts/open-shift/', {'cash_register_id': self.register_b.id}, format='json')

        self._auth(self.tenant_a['user'])
        response = self.client.get(
            '/api/v1/cash-shifts/for-register/', {'cash_register_id': self.register_b.id},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_without_handles_cash_capability_is_denied(self):
        cajero, _ = create_user_with_profile(
            'sincaja@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': False},
        )
        self._auth(cajero)
        response = self.client.get('/api/v1/cash-shifts/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_without_profile_is_denied(self):
        orphan = User.objects.create_user(email='sinprofile@test.com', password='x')
        self._auth(orphan)
        response = self.client.get('/api/v1/cash-shifts/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CashRegisterApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test',
            role=UserProfile.Role.ADMINISTRADOR, capabilities={'handles_cash': True},
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test',
            role=UserProfile.Role.ADMINISTRADOR, capabilities={'handles_cash': True},
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_create_cash_register_for_own_branch(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/cash-registers/', {'branch': self.tenant_a['branch'].id, 'name': 'Caja 1'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['company'], self.tenant_a['company'].id)

    def test_cannot_create_cash_register_pointing_to_other_tenant_branch(self):
        self._auth(self.tenant_a['user'])
        response = self.client.post(
            '/api/v1/cash-registers/',
            {'branch': self.tenant_b['branch'].id, 'name': 'Caja hackeada'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CashRegister.objects.filter(name='Caja hackeada').exists())

    def test_list_only_returns_own_tenant_registers(self):
        create_cash_register(self.tenant_a['branch'], name='A1')
        create_cash_register(self.tenant_b['branch'], name='B1')
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/cash-registers/')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['A1'])


class CurrentShiftEndpointTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'a@donchuy.test', capabilities={'handles_cash': True},
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'b@estrella.test', capabilities={'handles_cash': True},
        )
        self.register_a = create_cash_register(self.tenant_a['branch'])

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_returns_404_when_no_open_shift(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/cash-shifts/current/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_own_open_shift(self):
        shift = open_shift(user=self.tenant_a['user'], cash_register=self.register_a, opening_balance=Decimal('200'))
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/cash-shifts/current/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], shift.id)

    def test_does_not_return_another_cashiers_open_shift(self):
        other_cajero, _ = create_user_with_profile(
            'otro@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        open_shift(user=other_cajero, cash_register=self.register_a)
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/cash-shifts/current/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_does_not_return_closed_shift(self):
        shift = open_shift(user=self.tenant_a['user'], cash_register=self.register_a)
        close_shift(shift=shift, closing_user=self.tenant_a['user'], actual_closing_balance=Decimal('0'))
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/cash-shifts/current/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_administrador_without_any_capability_can_see_current_shift(self):
        # Bug real encontrado probando la app a mano con admin@fortuna.test
        # del seed: un ADMINISTRADOR recién creado (capabilities={}, el
        # estado correcto por default) recibía 403 "No tienes la capability
        # requerida" en vez de la visibilidad administrativa básica que le
        # corresponde. 404 aquí es el comportamiento correcto (no tiene
        # turno abierto) — lo importante es que NO sea 403.
        admin, _ = create_user_with_profile(
            'admin@donchuy.test', self.tenant_a['branch'],
            role=UserProfile.Role.ADMINISTRADOR, capabilities={},
        )
        self._auth(admin)
        response = self.client.get('/api/v1/cash-shifts/current/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        shift = open_shift(user=self.tenant_a['user'], cash_register=self.register_a)
        response = self.client.get('/api/v1/cash-shifts/current/')
        # El admin no es dueño del turno (lo abrió otro cajero) — current
        # sigue siendo "mi propio turno abierto", esto solo confirma que
        # ya no lo bloquea el permiso, no que vea turnos ajenos.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIsNotNone(shift)
