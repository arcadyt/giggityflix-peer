from django.contrib import admin
from django.utils.html import format_html

from giggityflix_mgmt_peer.apps.configuration.models import Configuration


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    """Admin configuration for the Configuration model."""

    list_display = ('key', 'display_typed_value', 'value_type', 'description', 'updated_at')
    list_filter = ('value_type', 'is_env_overridable')
    search_fields = ('key', 'value', 'description')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('key', 'value', 'value_type', 'description')
        }),
        ('Default and Environment', {
            'fields': ('default_value', 'is_env_overridable', 'env_variable')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def display_typed_value(self, obj):
        """Display the typed value in the admin list."""
        value = obj.get_typed_value()

        # Format the value nicely based on type
        if obj.value_type == Configuration.TYPE_STRING:
            return str(value)
        elif obj.value_type == Configuration.TYPE_BOOLEAN:
            return format_html(
                '<span style="color: {};">⚫</span> {}',
                'green' if value else 'red',
                str(value)
            )
        elif obj.value_type == Configuration.TYPE_LIST:
            if not value:
                return '[]'
            return format_html(
                '<span title="{}">[{}]</span>',
                ', '.join(str(item) for item in value),
                len(value)
            )
        elif obj.value_type == Configuration.TYPE_JSON:
            return format_html(
                '<span title="{}">JSON</span>',
                str(value)[:100]
            )
        else:
            return str(value)

    display_typed_value.short_description = 'Value'
