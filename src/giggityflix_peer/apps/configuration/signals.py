from django.dispatch import Signal

# Signal sent when a configuration value changes
configuration_changed = Signal(['key', 'value', 'value_type', 'timestamp'])