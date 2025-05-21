from rest_framework import serializers
from .models import Configuration


class ConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for the Configuration model."""

    typed_value = serializers.SerializerMethodField()
    typed_default_value = serializers.SerializerMethodField()

    class Meta:
        model = Configuration
        fields = (
            'key',
            'value',
            'default_value',
            'value_type',
            'description',
            'is_env_overridable',
            'env_variable',
            'created_at',
            'updated_at',
            'typed_value',
            'typed_default_value',
        )
        read_only_fields = ('created_at', 'updated_at', 'typed_value', 'typed_default_value')

    def get_typed_value(self, obj):
        """Get the typed value of the configuration."""
        return obj.get_typed_value()

    def get_typed_default_value(self, obj):
        """Get the typed default value of the configuration."""
        return obj.get_typed_default_value()

    def validate(self, data):
        """Validate that the value can be converted to the specified type."""
        value = data.get('value')
        value_type = data.get('value_type')

        if value is not None and value_type is not None:
            try:
                # Create a temporary instance to test conversion
                temp = Configuration(value=value, value_type=value_type)
                temp.get_typed_value()
            except Exception as e:
                raise serializers.ValidationError(f"Cannot convert value to {value_type}: {str(e)}")

        return data


class ConfigurationValueSerializer(serializers.Serializer):
    """Serializer for updating only the value of a configuration."""

    value = serializers.CharField(allow_null=True, required=False)

    def validate(self, data):
        key = self.context.get('key')
        value = data.get('value')

        if key:
            try:
                config = Configuration.objects.get(key=key)
                # Test that value can be converted to the right type
                temp = Configuration(value=value, value_type=config.value_type)
                temp.get_typed_value()
            except Configuration.DoesNotExist:
                raise serializers.ValidationError("Configuration key not found")
            except Exception as e:
                raise serializers.ValidationError(f"Cannot convert to {config.value_type}: {str(e)}")

        return data