"""Observación de sesión (ronda de 4 piezas, punto 4): no existía NINGÚN
mecanismo de ajuste manual de stock — ni modelo, ni endpoint, ni
frontend (StockTransfer/InventoryAdjustment seguían "pendientes de
construir" en arquitectura_tecnica_pos.md §3). Esto construye el
mecanismo real, con motivo obligatorio desde el día uno."""
from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import InventoryAdjustment
from catalog.services import InventoryAdjustmentError, adjust_batch_stock
from catalog.tests.factories import create_batch, create_product
from tenants.models import UserProfile
from tenants.tests.factories import create_full_tenant


class AdjustBatchStockServiceTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.product = create_product(self.tenant['company'], requires_batch=True)
        self.batch = create_batch(self.product, self.tenant['branch'], initial_quantity=10)

    def test_negative_delta_decreases_current_quantity(self):
        adjustment = adjust_batch_stock(
            batch=self.batch, quantity_delta=-3, reason=InventoryAdjustment.Reason.DAMAGE, actor=self.tenant['user'],
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 7)
        self.assertEqual(adjustment.quantity_before, 10)
        self.assertEqual(adjustment.quantity_after, 7)

    def test_positive_delta_increases_current_quantity(self):
        # Corrección de conteo: se encontró MÁS stock del registrado, no
        # solo bajas.
        adjustment = adjust_batch_stock(
            batch=self.batch, quantity_delta=5, reason=InventoryAdjustment.Reason.COUNT_CORRECTION,
            actor=self.tenant['user'],
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 15)
        self.assertEqual(adjustment.quantity_after, 15)

    def test_reason_and_actor_are_recorded(self):
        adjustment = adjust_batch_stock(
            batch=self.batch, quantity_delta=-2, reason=InventoryAdjustment.Reason.THEFT,
            actor=self.tenant['user'],
        )
        self.assertEqual(adjustment.reason, InventoryAdjustment.Reason.THEFT)
        self.assertEqual(adjustment.user, self.tenant['user'])
        self.assertEqual(adjustment.batch, self.batch)

    def test_zero_delta_is_rejected(self):
        with self.assertRaises(InventoryAdjustmentError):
            adjust_batch_stock(
                batch=self.batch, quantity_delta=0, reason=InventoryAdjustment.Reason.DAMAGE,
                actor=self.tenant['user'],
            )
        self.assertEqual(InventoryAdjustment.objects.count(), 0)

    def test_adjustment_that_would_go_negative_is_rejected(self):
        with self.assertRaises(InventoryAdjustmentError):
            adjust_batch_stock(
                batch=self.batch, quantity_delta=-99, reason=InventoryAdjustment.Reason.DAMAGE,
                actor=self.tenant['user'],
            )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 10)
        self.assertEqual(InventoryAdjustment.objects.count(), 0)

    def test_other_reason_without_detail_is_rejected(self):
        with self.assertRaises(InventoryAdjustmentError):
            adjust_batch_stock(
                batch=self.batch, quantity_delta=-1, reason=InventoryAdjustment.Reason.OTHER,
                actor=self.tenant['user'], reason_detail='   ',
            )
        self.assertEqual(InventoryAdjustment.objects.count(), 0)

    def test_other_reason_with_detail_is_accepted(self):
        adjustment = adjust_batch_stock(
            batch=self.batch, quantity_delta=-1, reason=InventoryAdjustment.Reason.OTHER,
            actor=self.tenant['user'], reason_detail='Producto dañado en traslado interno',
        )
        self.assertEqual(adjustment.reason_detail, 'Producto dañado en traslado interno')

    def test_damage_reason_does_not_require_detail(self):
        adjustment = adjust_batch_stock(
            batch=self.batch, quantity_delta=-1, reason=InventoryAdjustment.Reason.DAMAGE, actor=self.tenant['user'],
        )
        self.assertEqual(adjustment.reason_detail, '')


class AdjustBatchStockApiTests(APITestCase):
    def setUp(self):
        self.tenant = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.product = create_product(self.tenant['company'], requires_batch=True)
        self.batch = create_batch(self.product, self.tenant['branch'], initial_quantity=10)

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_administrador_can_adjust_stock_with_a_reason(self):
        self._auth(self.tenant['user'])
        response = self.client.post(
            f'/api/v1/batches/{self.batch.id}/adjust/',
            {'quantity_delta': -4, 'reason': 'DAMAGE'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['quantity_after'], 6)
        self.assertEqual(response.data['reason_label'], 'Merma/rotura')
        self.assertEqual(response.data['product_name'], self.product.name)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 6)

    def test_missing_reason_is_rejected_with_clean_400(self):
        self._auth(self.tenant['user'])
        response = self.client.post(
            f'/api/v1/batches/{self.batch.id}/adjust/', {'quantity_delta': -4}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 10)

    def test_other_reason_without_detail_is_rejected_with_clean_400(self):
        self._auth(self.tenant['user'])
        response = self.client.post(
            f'/api/v1/batches/{self.batch.id}/adjust/',
            {'quantity_delta': -1, 'reason': 'OTHER'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_plain_cajero_cannot_adjust_stock(self):
        from tenants.tests.factories import create_user_with_profile
        cajero, _ = create_user_with_profile('cajero@donchuy.test', self.tenant['branch'])
        self._auth(cajero)
        response = self.client.post(
            f'/api/v1/batches/{self.batch.id}/adjust/', {'quantity_delta': -1, 'reason': 'DAMAGE'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_can_adjust_stock(self):
        from tenants.tests.factories import create_user_with_profile
        supervisor, _ = create_user_with_profile(
            'supervisor@donchuy.test', self.tenant['branch'], capabilities={'can_authorize_exceptions': True},
        )
        self._auth(supervisor)
        response = self.client.post(
            f'/api/v1/batches/{self.batch.id}/adjust/', {'quantity_delta': -1, 'reason': 'COUNT_CORRECTION'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_adjust_a_batch_from_another_tenant(self):
        other_tenant = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self._auth(other_tenant['user'])
        response = self.client.post(
            f'/api/v1/batches/{self.batch.id}/adjust/', {'quantity_delta': -1, 'reason': 'DAMAGE'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_current_quantity_still_not_editable_via_plain_patch(self):
        # BatchSerializer sigue dejando current_quantity de solo lectura —
        # el único camino auditado es /adjust/.
        self._auth(self.tenant['user'])
        response = self.client.patch(
            f'/api/v1/batches/{self.batch.id}/', {'current_quantity': 999}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 10)
