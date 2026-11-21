from django.contrib import admin

from .models import Domain, Endpoint


class EndpointInline(admin.TabularInline):
    model = Endpoint
    extra = 1


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_url', 'auth_type', 'is_active')
    list_filter = ('auth_type', 'is_active')
    search_fields = ('name', 'base_url')
    inlines = [EndpointInline]
    fieldsets = (
        (None, {'fields': ('name', 'base_url', 'is_active', 'timeout')}),
        ('Credentials', {'fields': (
            'auth_type', 'token', 'username', 'password',
            'api_key_name', 'api_key_value', 'extra_headers',
        )}),
    )


@admin.register(Endpoint)
class EndpointAdmin(admin.ModelAdmin):
    list_display = ('method', 'path', 'domain', 'is_active')
    list_filter = ('method', 'is_active', 'domain')
    search_fields = ('path',)
