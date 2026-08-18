from django.contrib import admin

from customers.models import Client, CreditAccount, CreditMovement

admin.site.register(Client)
admin.site.register(CreditAccount)
admin.site.register(CreditMovement)
