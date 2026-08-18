"""Punto 7: resumen diario de stock bajo por correo, un tenant a la vez.

Mecanismo de programación elegido: cron del sistema operativo (crontab),
NO Celery Beat ni django-crontab. Ni Celery ni Redis existen todavía en
este proyecto (confirmado en requirements.txt) — introducirlos solo para
un correo diario sería la pieza de infraestructura más pesada del
proyecto para el trabajo más liviano. django-crontab tampoco se agrega:
es una dependencia nueva (aunque chica) para resolver algo que cron ya
resuelve gratis en cualquier servidor Linux, incluyendo Azure App Service
(vía WebJobs con trigger CRON) o Azure Container Apps Jobs. Ver
`documentacion/arquitectura_tecnica_pos.md` (sección de este punto) y
`documentacion/brief_infraestructura_carlos.md` para el comando de cron
recomendado y lo que Carlos necesita configurar en producción.

Ejecución local/dev (dentro del contenedor backend):
    docker compose exec backend python manage.py send_low_stock_digest
"""
from django.core.management.base import BaseCommand

from catalog.emails import LowStockDigestEmailError, send_low_stock_digest_email
from catalog.services import low_stock_products
from tenants.models import Company, UserProfile


class Command(BaseCommand):
    help = 'Manda el resumen diario de stock bajo al/los administrador(es) de cada tenant activo con productos en stock bajo.'

    def handle(self, *args, **options):
        sent_count = 0
        skipped_count = 0

        for company in Company.objects.filter(is_active=True):
            rows = low_stock_products(company=company)
            if not rows:
                # Sin esto, un tenant sano (sin nada bajo) recibiría un
                # correo vacío todos los días — ruido que entrena a
                # ignorarlo, justo lo que el punto 7 pide evitar.
                skipped_count += 1
                continue

            business_name = getattr(getattr(company, 'settings', None), 'business_name', '') or company.name
            admin_emails = (
                UserProfile.objects.filter(company=company, role=UserProfile.Role.ADMINISTRADOR, user__is_active=True)
                .values_list('user__email', flat=True)
            )

            for email in admin_emails:
                try:
                    send_low_stock_digest_email(business_name=business_name, to_email=email, rows=rows)
                    sent_count += 1
                except LowStockDigestEmailError as exc:
                    self.stderr.write(self.style.WARNING(str(exc)))

        self.stdout.write(self.style.SUCCESS(f'Resumen de stock bajo: {sent_count} correo(s) enviado(s), {skipped_count} tenant(s) sin stock bajo (sin correo).'))
