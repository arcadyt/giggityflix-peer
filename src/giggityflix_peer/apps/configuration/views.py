from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Configuration
from .serializers import ConfigurationSerializer, ConfigurationValueSerializer
from . import services

class ConfigurationViewSet(viewsets.ModelViewSet):
    """
    API endpoints for configuration management.
    
    list:        GET /configurations/
    retrieve:    GET /configurations/{key}/
    create:      POST /configurations/
    update:      PUT /configurations/{key}/
    partial:     PATCH /configurations/{key}/
    delete:      DELETE /configurations/{key}/
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
    
    # Override create to use service
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        data = serializer.validated_data
        key = data.get('key')
        
        # Use service to create
        success = services.set(
            key=key,
            value=data.get('value'),
            value_type=data.get('value_type'),
            description=data.get('description'),
            is_env_overridable=data.get('is_env_overridable'),
            env_variable=data.get('env_variable'),
            default_value=data.get('default_value')
        )
        
        if success:
            # Get the created object
            instance = get_object_or_404(Configuration, key=key)
            serializer = self.get_serializer(instance)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response({'error': 'Failed to create configuration'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Override update to use service
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # Extract validated data
        data = serializer.validated_data
        
        # Use service to update
        success = services.set(
            key=instance.key,
            value=data.get('value', instance.value),
            value_type=data.get('value_type', instance.value_type),
            description=data.get('description', instance.description),
            is_env_overridable=data.get('is_env_overridable', instance.is_env_overridable),
            env_variable=data.get('env_variable', instance.env_variable),
            default_value=data.get('default_value', instance.default_value)
        )
        
        if success:
            # Get the updated object
            instance = get_object_or_404(Configuration, key=instance.key)
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        
        return Response({'error': 'Failed to update configuration'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    # Override destroy to use service
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        success = services.delete(instance.key)
        
        if success:
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        return Response({'error': 'Failed to delete configuration'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['patch'])
    def value(self, request, key=None):
        """Update only the value field."""
        instance = self.get_object()
        serializer = ConfigurationValueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Use service to update value only
        success = services.set(key, serializer.validated_data.get('value'))
        
        if success:
            return Response(status=status.HTTP_200_OK)
        
        return Response({'error': 'Failed to update value'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'])
    def dict(self, request):
        """Return all configs as plain dict {key: typed_value}."""
        return Response(services.get_all())