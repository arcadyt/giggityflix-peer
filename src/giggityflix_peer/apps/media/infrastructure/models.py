"""Django ORM models for media persistence."""
from django.db import models

from ..domain.models import MediaStatus, MediaType


class MediaFile(models.Model):
    """ORM model for media files."""
    luid = models.CharField(max_length=64, primary_key=True)
    catalog_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    path = models.TextField()
    relative_path = models.TextField(null=True, blank=True)
    size_bytes = models.BigIntegerField()
    media_type = models.CharField(
        max_length=20,
        choices=[(t.value, t.name) for t in MediaType],
        null=False
    )
    status = models.CharField(
        max_length=20,
        choices=[(s.value, s.name) for s in MediaStatus],
        default=MediaStatus.PENDING.value
    )
    
    # File metadata
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(null=True, blank=True)
    
    # Media metadata
    duration_seconds = models.FloatField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    codec = models.CharField(max_length=64, null=True, blank=True)
    bitrate = models.IntegerField(null=True, blank=True)
    framerate = models.FloatField(null=True, blank=True)
    
    # Streaming stats
    view_count = models.IntegerField(default=0)
    last_viewed = models.DateTimeField(null=True, blank=True)
    
    # Error information
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['media_type']),
            models.Index(fields=['status']),
            models.Index(fields=['catalog_id']),
        ]
        app_label = 'media'
        
    def __str__(self):
        return f"{self.luid} - {self.path}"


class MediaHash(models.Model):
    """ORM model for media file hashes."""
    media = models.ForeignKey(
        MediaFile, 
        on_delete=models.CASCADE, 
        related_name='hashes'
    )
    algorithm = models.CharField(max_length=32)
    hash_value = models.CharField(max_length=128)
    
    class Meta:
        unique_together = ('media', 'algorithm')
        app_label = 'media'
        
    def __str__(self):
        return f"{self.algorithm} hash for {self.media.luid}"


class Screenshot(models.Model):
    """ORM model for media screenshots."""
    id = models.CharField(max_length=64, primary_key=True)
    media = models.ForeignKey(
        MediaFile,
        on_delete=models.CASCADE,
        related_name='screenshots'
    )
    path = models.TextField()
    timestamp = models.FloatField()
    width = models.IntegerField()
    height = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        app_label = 'media'
    
    def __str__(self):
        return f"Screenshot {self.id} for {self.media.luid}"
