from django.test import TestCase

from audit.models import AuditLog
from audit.services import log_action
from tenants.tests.factories import create_full_tenant


class LogActionServiceTests(TestCase):
    def setUp(self):
        self.tenant = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')

    def test_log_action_with_instance_fills_model_name_and_object_id(self):
        entry = log_action(
            company=self.tenant['company'],
            action='branch.update',
            user=self.tenant['user'],
            instance=self.tenant['branch'],
            changes={'name': ['Centro', 'Centro 2']},
        )
        self.assertEqual(entry.company, self.tenant['company'])
        self.assertEqual(entry.user, self.tenant['user'])
        self.assertEqual(entry.action, 'branch.update')
        self.assertEqual(entry.model_name, 'tenants.Branch')
        self.assertEqual(entry.object_id, str(self.tenant['branch'].id))
        self.assertEqual(entry.changes, {'name': ['Centro', 'Centro 2']})

    def test_log_action_without_instance_leaves_target_fields_blank(self):
        entry = log_action(company=self.tenant['company'], action='auth.login', user=self.tenant['user'])
        self.assertEqual(entry.model_name, '')
        self.assertEqual(entry.object_id, '')
        self.assertEqual(entry.changes, {})

    def test_log_action_without_user_is_allowed(self):
        # Acciones de sistema (jobs, sync) no siempre tienen un usuario detrás.
        entry = log_action(company=self.tenant['company'], action='system.cleanup')
        self.assertIsNone(entry.user)

    def test_entries_are_ordered_most_recent_first(self):
        first = log_action(company=self.tenant['company'], action='first')
        second = log_action(company=self.tenant['company'], action='second')
        self.assertEqual(list(AuditLog.objects.filter(company=self.tenant['company'])), [second, first])


class AuditLogIsolationTests(TestCase):
    """Mismo estándar que tenants: la bitácora de un tenant no debe filtrarse
    a otro, ni siquiera en modo lectura."""

    def setUp(self):
        self.tenant_a = create_full_tenant('Abarrotes Don Chuy', 'Centro', 'admin@donchuy.test')
        self.tenant_b = create_full_tenant('Papelería La Estrella', 'Norte', 'admin@estrella.test')
        self.entry_a = log_action(company=self.tenant_a['company'], action='shift.open', user=self.tenant_a['user'])
        self.entry_b = log_action(company=self.tenant_b['company'], action='shift.open', user=self.tenant_b['user'])

    def test_for_user_only_returns_own_tenant_entries(self):
        visible = AuditLog.objects.for_user(self.tenant_a['user'])
        self.assertEqual(list(visible), [self.entry_a])
        self.assertNotIn(self.entry_b, visible)

    def test_for_company_only_returns_own_tenant_entries(self):
        visible = AuditLog.objects.for_company(self.tenant_b['company'])
        self.assertEqual(list(visible), [self.entry_b])
        self.assertNotIn(self.entry_a, visible)

    def test_unscoped_manager_sees_both_tenants(self):
        self.assertEqual(AuditLog.objects.count(), 2)
