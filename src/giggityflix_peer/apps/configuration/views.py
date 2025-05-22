from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Configuration
from .serializers import ConfigurationSerializer, ConfigurationValueSerializer
from . import services


class ConfigurationViewSet(mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """
    API endpoints for configuration management.
    
    Only allows reading configurations and patching values.
    No creation or deletion of configuration keys via API.
    
    list:        GET /configurations/
    retrieve:    GET /configurations/{key}/
    value:       PATCH /configurations/{key}/value/
    dict:        GET /configurations/dict/
    """
    queryset = Configuration.objects.all()
    serializer_class = ConfigurationSerializer
    lookup_field = 'key'
    
    def get_queryset(self):
        # Allow filtering by value_type
        queryset = super().get_queryset()
        value_type = self.request.query_params.get('value_type')
        if value_type:
            queryset = queryset.filter(value_type=value_type)
        return queryset
    
    # Override to disable create
    def create(self, request, *args, **kwargs):
        return Response(
            {'error': 'Configuration creation via API not allowed. Use Django admin or management commands.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    # Override to disable update
    def update(self, request, *args, **kwargs):
        return Response(
            {'error': 'Use PATCH /configurations/{key}/value/ to update configuration values.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    def partial_update(self, request, *args, **kwargs):
        return Response(
            {'error': 'Use PATCH /configurations/{key}/value/ to update configuration values.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    # Override to disable destroy
    def destroy(self, request, *args, **kwargs):
        return Response(
            {'error': 'Configuration deletion via API not allowed. Use Django admin or management commands.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    @action(detail=True, methods=['patch'])
    def value(self, request, key=None):
        """Update only the value field of a configuration."""
        instance = self.get_object()
        serializer = ConfigurationValueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Use service to update value only
        success = services.set(key, serializer.validated_data.get('value'))
        
        if success:
            # Return updated configuration
            updated_instance = get_object_or_404(Configuration, key=key)
            response_serializer = self.get_serializer(updated_instance)
            return Response(response_serializer.data)
        
        return Response(
            {'error': 'Failed to update configuration value'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    @action(detail=False, methods=['get'])
    def dict(self, request):
        """Return all configurations as plain dictionary {key: typed_value}."""
        return Response(services.get_all())
