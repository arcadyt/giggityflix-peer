from django.db import models
from django.utils import timezone
import json
from .signals import configuration_changed

class Configuration(models.Model):
    """Django ORM model for configuration settings with type conversion."""
    # Type constants
    TYPE_STRING = 'string'
    TYPE_INTEGER = 'integer'
    TYPE_FLOAT = 'float'
    TYPE_BOOLEAN = 'boolean'
    TYPE_JSON = 'json'
    TYPE_LIST = 'list'

    TYPE_CHOICES = [
        (TYPE_STRING, 'String'),
        (TYPE_INTEGER, 'Integer'),
        (TYPE_FLOAT, 'Float'),
        (TYPE_BOOLEAN, 'Boolean'),
        (TYPE_JSON, 'JSON'),
        (TYPE_LIST, 'List'),
    ]

    # Fields
    key = models.CharField(max_length=255, primary_key=True, 
                          help_text='Configuration property key')
    value = models.TextField(null=True, blank=True, 
                            help_text='Current value of the configuration property')
    default_value = models.TextField(null=True, blank=True, 
                                    help_text='Default value if not specified')
    value_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_STRING,
                                 help_text='Type of the configuration value')
    description = models.TextField(null=True, blank=True, 
                                  help_text='Description of the configuration property')
    is_env_overridable = models.BooleanField(default=True, 
                                            help_text='Whether environment variables can override this configuration')
    env_variable = models.CharField(max_length=255, null=True, blank=True,
                                   help_text='Environment variable name to use for override')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_typed_value(self):
        """Get the value converted to its specified type."""
        if self.value is None:
            return self.get_typed_default_value()
        return self._convert_value(self.value, self.value_type)

    def get_typed_default_value(self):
        """Get the default value converted to its specified type."""
        if self.default_value is None:
            return None
        return self._convert_value(self.default_value, self.value_type)

    def set_typed_value(self, value):
        """Set the value, converting it to string for storage."""
        old_value = self.get_typed_value()
        self.value = self._to_storage_format(value)
        return old_value

    def _to_storage_format(self, value):
        """Convert any value to string format for storage."""
        if value is None:
            return None

        if self.value_type == self.TYPE_STRING:
            return str(value)
        elif self.value_type == self.TYPE_INTEGER:
            return str(int(value))
        elif self.value_type == self.TYPE_FLOAT:
            return str(float(value))
        elif self.value_type == self.TYPE_BOOLEAN:
            return str(bool(value)).lower()
        elif self.value_type == self.TYPE_JSON:
            return json.dumps(value)
        elif self.value_type == self.TYPE_LIST:
            if isinstance(value, list):
                return ",".join(str(item) for item in value)
            return str(value)
        return str(value)

    @staticmethod
    def _convert_value(value_str, value_type):
        """Convert string value to the appropriate type."""
        if value_str is None:
            return None

        try:
            if value_type == Configuration.TYPE_STRING:
                return value_str
            elif value_type == Configuration.TYPE_INTEGER:
                return int(value_str)
            elif value_type == Configuration.TYPE_FLOAT:
                return float(value_str)
            elif value_type == Configuration.TYPE_BOOLEAN:
                return value_str.lower() in ('true', 'yes', '1', 't', 'y')
            elif value_type == Configuration.TYPE_JSON:
                return json.loads(value_str)
            elif value_type == Configuration.TYPE_LIST:
                if not value_str:
                    return []
                return [item.strip() for item in value_str.split(',')]
            else:
                return value_str
        except Exception:
            # If conversion fails, return original string
            return value_str

    def save(self, *args, **kwargs):
        """Override save to send signal when configuration changes."""
        # Call the Django save method
        super().save(*args, **kwargs)
        
        # Send the signal with the typed value
        configuration_changed.send(
            sender=self.__class__,
            key=self.key,
            value=self.get_typed_value(),
            value_type=self.value_type,
            timestamp=timezone.now()
        )

    class Meta:
        ordering = ['key']
        verbose_name = 'Configuration'
        verbose_name_plural = 'Configurations'
        app_label = 'configuration'

    def __str__(self):
        return f"{self.key}: {self.get_typed_value()}"
