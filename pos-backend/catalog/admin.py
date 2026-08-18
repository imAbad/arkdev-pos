from django.contrib import admin

from catalog.models import Batch, Category, Product, Supplier

admin.site.register(Category)
admin.site.register(Supplier)
admin.site.register(Product)
admin.site.register(Batch)
