"""Serializers for media app API endpoints."""
from rest_framework import serializers

from ..infrastructure.models import MediaFile, Screenshot


class MediaFileSerializer(serializers.ModelSerializer):
    """Serializer for MediaFile model."""
    hashes = serializers.SerializerMethodField()
    
    class Meta:
        model = MediaFile
        fields = [
            'luid', 'catalog_id', 'path', 'relative_path', 'size_bytes',
            'media_type', 'status', 'created_at', 'modified_at', 'last_accessed',
            'duration_seconds', 'width', 'height', 'codec', 'bitrate', 'framerate',
            'view_count', 'last_viewed', 'error_message', 'hashes'
        ]
        read_only_fields = [
            'luid', 'created_at', 'modified_at', 'last_accessed',
            'view_count', 'last_viewed'
        ]
    
    def get_hashes(self, obj):
        """Get hashes as a dictionary."""
        return {h.algorithm: h.hash_value for h in obj.hashes.all()}


class ScreenshotSerializer(serializers.ModelSerializer):
    """Serializer for Screenshot model."""
    media_luid = serializers.CharField(source='media.luid')
    url = serializers.SerializerMethodField()
    
    class Meta:
        model = Screenshot
        fields = [
            'id', 'media_luid', 'path', 'timestamp', 'width', 'height',
            'created_at', 'url'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_url(self, obj):
        """Get screenshot URL."""
        import os
        from pathlib import Path
        return f"/screenshots/{Path(obj.path).name}"


class MediaStatsSerializer(serializers.Serializer):
    """Serializer for media statistics."""
    total_files = serializers.IntegerField()
    total_size_bytes = serializers.IntegerField()
    by_type = serializers.DictField(
        child=serializers.IntegerField()
    )
    by_status = serializers.DictField(
        child=serializers.IntegerField()
    )
