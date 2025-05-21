from django.db import models


class PhysicalDrive(models.Model):
    """Django ORM model representing a physical drive."""
    id = models.CharField(max_length=255, primary_key=True)
    manufacturer = models.CharField(max_length=255, blank=True, default="Unknown")
    model = models.CharField(max_length=255, blank=True, default="Unknown")
    serial = models.CharField(max_length=255, blank=True, default="Unknown")
    size_bytes = models.BigIntegerField(default=0)
    filesystem_type = models.CharField(max_length=50, blank=True, default="Unknown")
    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'drive_detection'

    def __str__(self):
        return f"{self.id} - {self.model} ({self.size_bytes} bytes)"


class Partition(models.Model):
    """Django ORM model representing a partition or mount point."""
    mount_point = models.CharField(max_length=255, primary_key=True)
    physical_drive = models.ForeignKey(
        PhysicalDrive,
        related_name="partitions",
        on_delete=models.CASCADE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'drive_detection'

    def __str__(self):
        return f"{self.mount_point} -> {self.physical_drive.id}"
