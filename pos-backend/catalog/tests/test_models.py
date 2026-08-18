from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Batch, Category, Product
from catalog.tests.factories import create_batch, create_category, create_product
from tenants.tests.factories import create_branch, create_company


class CategoryModelTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')

    def test_slug_is_auto_generated_from_name(self):
        category = create_category(self.company, name='Frutas y Verduras')
        self.assertEqual(category.slug, 'frutas-y-verduras')

    def test_name_is_unique_per_company(self):
        create_category(self.company, name='Lácteos')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_category(self.company, name='Lácteos')

    def test_same_category_name_is_allowed_across_different_tenants(self):
        other_company = create_company('Papelería La Estrella')
        create_category(self.company, name='General')
        # No debe explotar: el unique_together es (company, name), no name solo.
        create_category(other_company, name='General')
        self.assertEqual(Category.objects.count(), 2)


class ProductModelTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')

    def test_sku_is_unique_per_company(self):
        create_product(self.company, sku='ABC-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_product(self.company, sku='ABC-1', name='Otro producto')

    def test_same_sku_is_allowed_across_different_tenants(self):
        other_company = create_company('Papelería La Estrella')
        create_product(self.company, sku='ABC-1')
        create_product(other_company, sku='ABC-1')
        self.assertEqual(Product.objects.count(), 2)

    def test_multiple_products_without_barcode_are_allowed(self):
        # barcode nullable + constraint condicional (barcode__isnull=False):
        # dos productos sin código de barras en la misma company no chocan.
        create_product(self.company, sku='A', barcode=None)
        create_product(self.company, sku='B', barcode=None)
        self.assertEqual(Product.objects.count(), 2)

    def test_barcode_is_unique_per_company_when_present(self):
        create_product(self.company, sku='A', barcode='7501234567890')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_product(self.company, sku='B', barcode='7501234567890')

    def test_all_documented_unit_types_are_valid_choices(self):
        for unit_type, _ in Product.UnitType.choices:
            with self.subTest(unit_type=unit_type):
                product = create_product(self.company, sku=f'SKU-{unit_type}', unit_type=unit_type)
                product.full_clean()

    def test_variant_attributes_defaults_to_null(self):
        product = create_product(self.company)
        self.assertIsNone(product.variant_attributes)

    def test_variant_attributes_accepts_arbitrary_json(self):
        product = create_product(
            self.company, sku='VAR-1', variant_attributes={'color': 'rojo', 'talla': 'M'},
        )
        product.refresh_from_db()
        self.assertEqual(product.variant_attributes, {'color': 'rojo', 'talla': 'M'})


class RelatedProductsSymmetricTests(TestCase):
    """Punto 5: cross-sell simple — relación elegida simétrica a propósito
    (ver docstring de Product.related_products). Esto se prueba a nivel de
    modelo porque es comportamiento de Django (ManyToManyField('self') sin
    symmetrical=False), no lógica propia — vale la pena fijarlo con un
    test explícito para que nadie lo cambie sin darse cuenta."""

    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')

    def test_adding_a_relation_is_visible_from_both_sides(self):
        pan = create_product(self.company, name='Pan de caja', sku='PAN-1')
        mantequilla = create_product(self.company, name='Mantequilla', sku='MANT-1')

        pan.related_products.add(mantequilla)

        self.assertIn(mantequilla, pan.related_products.all())
        self.assertIn(pan, mantequilla.related_products.all())

    def test_removing_a_relation_removes_it_from_both_sides(self):
        pan = create_product(self.company, name='Pan de caja', sku='PAN-2')
        mantequilla = create_product(self.company, name='Mantequilla', sku='MANT-2')
        pan.related_products.add(mantequilla)

        pan.related_products.remove(mantequilla)

        self.assertNotIn(mantequilla, pan.related_products.all())
        self.assertNotIn(pan, mantequilla.related_products.all())

    def test_a_product_with_no_related_products_returns_empty(self):
        solo = create_product(self.company, name='Producto solitario', sku='SOLO-1')
        self.assertEqual(list(solo.related_products.all()), [])


class RequiresBatchIndependenceTests(TestCase):
    """El pedido explícito: requires_batch=False no debe romper nada aunque
    Batch exista como modelo en el sistema — y tampoco hay ninguna
    constraint de BD que ate Product a Batch en ningún sentido."""

    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)

    def test_product_with_requires_batch_false_saves_and_has_no_batches(self):
        product = create_product(self.company, sku='GRANEL-1', requires_batch=False)
        self.assertFalse(product.requires_batch)
        self.assertEqual(product.batches.count(), 0)
        # Ni full_clean ni save exigen nada relacionado a Batch:
        product.full_clean()

    def test_product_with_requires_batch_true_can_exist_without_any_batch_yet(self):
        # requires_batch es una bandera informativa para el flujo de venta
        # (punto 4, sales) — no hay ninguna constraint de BD en Batch/Product
        # que fuerce su existencia todavía.
        product = create_product(self.company, sku='LOTE-1', requires_batch=True)
        self.assertEqual(product.batches.count(), 0)

    def test_product_with_requires_batch_true_can_have_batches(self):
        product = create_product(self.company, sku='LOTE-2', requires_batch=True)
        create_batch(product, self.branch)
        self.assertEqual(product.batches.count(), 1)

    def test_product_with_requires_batch_false_can_still_have_batches_if_needed(self):
        # requires_batch=False no bloquea crear un Batch si por alguna razón
        # se necesita (ej. dato histórico) — es una bandera de flujo de
        # venta, no una restricción de integridad.
        product = create_product(self.company, sku='GRANEL-2', requires_batch=False)
        create_batch(product, self.branch)
        self.assertEqual(product.batches.count(), 1)


class BatchModelTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')
        self.branch = create_branch(self.company)
        self.product = create_product(self.company)

    def test_current_quantity_is_set_from_initial_quantity_on_create(self):
        batch = create_batch(self.product, self.branch, initial_quantity=50)
        self.assertEqual(batch.current_quantity, 50)

    def test_company_is_derived_from_product(self):
        batch = create_batch(self.product, self.branch)
        self.assertEqual(batch.company_id, self.company.id)

    def test_batch_number_is_unique_per_product(self):
        create_batch(self.product, self.branch, batch_number='L-1')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_batch(self.product, self.branch, batch_number='L-1')

    def test_same_batch_number_allowed_on_different_products(self):
        other_product = create_product(self.company, sku='OTRO-SKU')
        create_batch(self.product, self.branch, batch_number='L-1')
        create_batch(other_product, self.branch, batch_number='L-1')
        self.assertEqual(Batch.objects.filter(batch_number='L-1').count(), 2)

    def test_is_expired_and_can_be_sold(self):
        expired = create_batch(
            self.product, self.branch, batch_number='EXP-1',
            expiration_date=timezone.localdate() - timedelta(days=1),
        )
        fresh = create_batch(
            self.product, self.branch, batch_number='FRESH-1',
            expiration_date=timezone.localdate() + timedelta(days=10),
        )
        self.assertTrue(expired.is_expired)
        self.assertFalse(expired.can_be_sold())
        self.assertFalse(fresh.is_expired)
        self.assertTrue(fresh.can_be_sold())

    def test_zero_stock_cannot_be_sold_even_if_fresh(self):
        batch = create_batch(self.product, self.branch, initial_quantity=5)
        batch.current_quantity = 0
        batch.save()
        self.assertFalse(batch.can_be_sold())


class ProductImageUploadTests(TestCase):
    def setUp(self):
        self.company = create_company('Abarrotes Don Chuy')

    def test_product_saves_without_an_image(self):
        product = create_product(self.company)
        self.assertFalse(product.image)

    def test_image_upload_path_is_prefixed_by_tenant(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_media_root:
            with override_settings(MEDIA_ROOT=tmp_media_root):
                image_file = SimpleUploadedFile(
                    'logo.png',
                    (
                        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
                        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00'
                        b'\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
                    ),
                    content_type='image/png',
                )
                product = create_product(self.company, sku='IMG-1', image=image_file)
                self.assertTrue(product.image.name.startswith(f'tenant_{self.company.id}/products/'))
