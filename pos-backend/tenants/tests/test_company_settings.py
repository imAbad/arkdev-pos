"""Personalización visual de CompanySettings (business_name/logo/accent_color)
— mismo estándar de aislamiento que el resto del proyecto: un tenant no
debe poder ver ni editar la personalización de otro."""
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import CompanySettings, UserProfile
from tenants.tests.factories import create_full_tenant, create_user_with_profile

_PNG_BYTES = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00'
    b'\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
)


class CompanySettingsBrandingModelTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')

    def test_accent_color_defaults_to_reference_blue(self):
        self.assertEqual(self.tenant['settings'].accent_color, '#1E5B94')

    def test_business_name_defaults_to_blank_and_can_differ_from_company_name(self):
        settings_ = self.tenant['settings']
        self.assertEqual(settings_.business_name, '')
        settings_.business_name = 'Don Chuy Abarrotes y Miscelánea'
        settings_.full_clean()
        settings_.save()
        settings_.refresh_from_db()
        self.assertNotEqual(settings_.business_name, settings_.company.name)

    def test_accent_color_rejects_non_hex_values(self):
        settings_ = self.tenant['settings']
        settings_.accent_color = 'azul'
        with self.assertRaises(ValidationError):
            settings_.full_clean()

    def test_accent_color_rejects_short_hex(self):
        settings_ = self.tenant['settings']
        settings_.accent_color = '#fff'
        with self.assertRaises(ValidationError):
            settings_.full_clean()

    def test_logo_upload_path_is_prefixed_by_tenant(self):
        with tempfile.TemporaryDirectory() as tmp_media_root:
            with override_settings(MEDIA_ROOT=tmp_media_root):
                settings_ = self.tenant['settings']
                settings_.logo = SimpleUploadedFile('logo.png', _PNG_BYTES, content_type='image/png')
                settings_.save()
                self.assertTrue(
                    settings_.logo.name.startswith(f'tenant_{self.tenant["company"].id}/branding/'),
                )

    def test_settings_without_logo_is_valid(self):
        settings_ = self.tenant['settings']
        self.assertFalse(settings_.logo)
        settings_.full_clean()


class CompanySettingsBrandingApiTests(APITestCase):
    def setUp(self):
        self.tenant_a = create_full_tenant(
            'Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test', role=UserProfile.Role.ADMINISTRADOR,
        )
        self.tenant_b = create_full_tenant(
            'Papelería La Estrella', 'Norte', 'admin@estrella.test', role=UserProfile.Role.ADMINISTRADOR,
        )

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_retrieve_includes_branding_fields(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get(f"/api/v1/company-settings/{self.tenant_a['settings'].id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['accent_color'], '#1E5B94')
        self.assertIn('business_name', response.data)
        self.assertIn('logo', response.data)

    def test_can_update_own_branding(self):
        self._auth(self.tenant_a['user'])
        response = self.client.patch(
            f"/api/v1/company-settings/{self.tenant_a['settings'].id}/",
            {'business_name': 'Don Chuy Abarrotes', 'accent_color': '#0F4C81'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tenant_a['settings'].refresh_from_db()
        self.assertEqual(self.tenant_a['settings'].business_name, 'Don Chuy Abarrotes')
        self.assertEqual(self.tenant_a['settings'].accent_color, '#0F4C81')

    def test_cannot_retrieve_other_tenant_branding(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get(f"/api/v1/company-settings/{self.tenant_b['settings'].id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_update_other_tenant_branding(self):
        self._auth(self.tenant_a['user'])
        response = self.client.patch(
            f"/api/v1/company-settings/{self.tenant_b['settings'].id}/",
            {'business_name': 'Hackeado'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.tenant_b['settings'].refresh_from_db()
        self.assertNotEqual(self.tenant_b['settings'].business_name, 'Hackeado')

    def test_list_only_returns_own_tenant_settings(self):
        self._auth(self.tenant_a['user'])
        response = self.client.get('/api/v1/company-settings/')
        ids = [row['id'] for row in response.data['results']]
        self.assertEqual(ids, [self.tenant_a['settings'].id])

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get('/api/v1/company-settings/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_plain_cajero_can_read_branding_but_not_write_it(self):
        # Punto 3/12: branding y feature flags son configuración de
        # negocio, exclusiva de ADMINISTRADOR — un CAJERO puede seguir
        # leyendo (AppHeader lo necesita para pintar la marca sin
        # importar el rol de quien esté logueado) pero no editarlo. Bug
        # real encontrado al revisar el viewset: no tenía NINGÚN
        # permission_classes propio antes de este punto, heredaba el
        # default de DRF (IsAuthenticated a secas) — cualquier cajero
        # podía hacer PATCH aquí.
        cajero, _ = create_user_with_profile(
            'cajero@donchuy.test', self.tenant_a['branch'], capabilities={'handles_cash': True},
        )
        self._auth(cajero)

        get_response = self.client.get(f"/api/v1/company-settings/{self.tenant_a['settings'].id}/")
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        patch_response = self.client.patch(
            f"/api/v1/company-settings/{self.tenant_a['settings'].id}/",
            {'business_name': 'Nombre no autorizado'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)
        self.tenant_a['settings'].refresh_from_db()
        self.assertNotEqual(self.tenant_a['settings'].business_name, 'Nombre no autorizado')

    def test_administrador_can_toggle_enabled_modules(self):
        self._auth(self.tenant_a['user'])
        response = self.client.patch(
            f"/api/v1/company-settings/{self.tenant_a['settings'].id}/",
            {'enabled_modules': {'cfdi': True, 'multiple_branches': False}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.tenant_a['settings'].refresh_from_db()
        self.assertEqual(
            self.tenant_a['settings'].enabled_modules, {'cfdi': True, 'multiple_branches': False},
        )

    def test_enabled_modules_defaults_to_empty_dict(self):
        self.assertEqual(self.tenant_a['settings'].enabled_modules, {})
