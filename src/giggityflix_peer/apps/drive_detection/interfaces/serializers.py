"""Serializers for drive detection."""
from rest_framework import serializers

from giggityflix_mgmt_peer.apps.drive_detection.infrastructure.orm import PhysicalDrive, Partition


class PhysicalDriveSerializer(serializers.ModelSerializer):
    """Serializer for PhysicalDrive model."""

    class Meta:
        model = PhysicalDrive
        fields = ['id', 'manufacturer', 'model', 'serial', 'size_bytes', 'filesystem_type', 'detected_at', 'updated_at']
        read_only_fields = ['detected_at', 'updated_at']


class PartitionSerializer(serializers.ModelSerializer):
    """Serializer for Partition model."""

    physical_drive_detail = PhysicalDriveSerializer(source='physical_drive', read_only=True)

    class Meta:
        model = Partition
        fields = ['mount_point', 'physical_drive', 'physical_drive_detail', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class DriveStatsSerializer(serializers.Serializer):
    """Serializer for drive statistics."""

    total_drives = serializers.IntegerField()
    total_partitions = serializers.IntegerField()
    total_storage_bytes = serializers.IntegerField()
