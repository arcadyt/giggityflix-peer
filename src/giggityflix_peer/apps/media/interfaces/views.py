"""API views for media app."""
from django.db.models import Count, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..application.screenshot_service import ScreenshotService, get_screenshot_service
from ..domain.models import MediaStatus
from ..infrastructure.models import MediaFile, Screenshot
from .serializers import MediaFileSerializer, MediaStatsSerializer, ScreenshotSerializer


class MediaFileViewSet(viewsets.ModelViewSet):
    """ViewSet for MediaFile model."""
    queryset = MediaFile.objects.all()
    serializer_class = MediaFileSerializer
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get media statistics."""
        # Calculate stats
        total_files = MediaFile.objects.count()
        total_size = MediaFile.objects.aggregate(total=Sum('size_bytes'))['total'] or 0
        
        # Count by type
        by_type = {}
        type_counts = MediaFile.objects.values('media_type').annotate(count=Count('luid'))
        for item in type_counts:
            by_type[item['media_type']] = item['count']
        
        # Count by status
        by_status = {}
        status_counts = MediaFile.objects.values('status').annotate(count=Count('luid'))
        for item in status_counts:
            by_status[item['status']] = item['count']
        
        # Create stats object
        stats = {
            'total_files': total_files,
            'total_size_bytes': total_size,
            'by_type': by_type,
            'by_status': by_status
        }
        
        serializer = MediaStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def capture_screenshots(self, request, pk=None):
        """Capture screenshots for a media file."""
        try:
            media_file = self.get_object()
            
            # Get quantity from query params or default to 3
            quantity = int(request.query_params.get('quantity', 3))
            
            # Get screenshot service
            screenshot_service = get_screenshot_service()
            
            # Capture screenshots
            screenshots = screenshot_service.capture_for_media(media_file.luid, quantity)
            
            # Serialize screenshots
            serializer = ScreenshotSerializer(screenshots, many=True)
            return Response(serializer.data)
        
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ScreenshotViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for Screenshot model."""
    queryset = Screenshot.objects.all()
    serializer_class = ScreenshotSerializer
    
    def get_queryset(self):
        """Filter queryset by media_luid if provided."""
        queryset = super().get_queryset()
        media_luid = self.request.query_params.get('media_luid')
        if media_luid:
            queryset = queryset.filter(media_id=media_luid)
        return queryset
