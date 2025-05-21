from django.db.models import Sum
from rest_framework import viewsets, mixins, status
from rest_framework.decorators import action
from rest_framework.response import Response

from ..drive_detection.application.drive_service import get_drive_service
from ..drive_detection.infrastructure.orm import PhysicalDrive, Partition
from ..drive_detection.interfaces.serializers import PhysicalDriveSerializer, PartitionSerializer, DriveStatsSerializer


class PhysicalDriveViewSet(mixins.ListModelMixin,
                           mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    queryset = PhysicalDrive.objects.all()
    serializer_class = PhysicalDriveSerializer

    @action(detail=False, methods=['post'])
    def refresh(self, request):
        """Refresh drives by detecting them again."""
        drive_service = get_drive_service()
        result = drive_service.detect_and_persist_drives()
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get drive statistics."""
        stats = {
            'total_drives': PhysicalDrive.objects.count(),
            'total_partitions': Partition.objects.count(),
            'total_storage_bytes': PhysicalDrive.objects.aggregate(
                total=Sum('size_bytes'))['total'] or 0
        }
        serializer = DriveStatsSerializer(stats)
        return Response(serializer.data)


class PartitionViewSet(mixins.ListModelMixin,
                       mixins.RetrieveModelMixin,
                       viewsets.GenericViewSet):
    queryset = Partition.objects.all()
    serializer_class = PartitionSerializer
