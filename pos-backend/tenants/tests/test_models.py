from django.db import IntegrityError, transaction
from django.test import TestCase

from tenants.models import UserProfile
from tenants.tests.factories import (
    create_branch,
    create_company,
    create_company_settings,
    create_user_with_profile,
)


class UserProfileCompanyDerivationTests(TestCase):
    def test_company_is_derived_from_branch_on_save(self):
        company = create_company('Abarrotes Don Chuy')
        branch = create_branch(company)
        _, profile = create_user_with_profile('cajero@donchuy.test', branch)
        self.assertEqual(profile.company_id, company.id)

    def test_capability_properties_default_to_false(self):
        company = create_company('Abarrotes Don Chuy')
        branch = create_branch(company)
        _, profile = create_user_with_profile('cajero@donchuy.test', branch)
        self.assertFalse(profile.handles_cash)
        self.assertFalse(profile.can_authorize_exceptions)

    def test_supervisor_is_modeled_as_capability_not_role(self):
        # Ver decisiones_post_auditoria.md #5: Supervisor no es un choice de
        # role aparte, es can_authorize_exceptions=True sobre un CAJERO.
        company = create_company('Abarrotes Don Chuy')
        branch = create_branch(company)
        _, profile = create_user_with_profile(
            'supervisor@donchuy.test',
            branch,
            role=UserProfile.Role.CAJERO,
            capabilities={'can_authorize_exceptions': True, 'handles_cash': True},
        )
        self.assertEqual(profile.role, UserProfile.Role.CAJERO)
        self.assertTrue(profile.can_authorize_exceptions)
        self.assertTrue(profile.handles_cash)


class CompanySettingsUniquenessTests(TestCase):
    def test_only_one_settings_row_per_company(self):
        company = create_company('Abarrotes Don Chuy')
        create_company_settings(company)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                create_company_settings(company)
