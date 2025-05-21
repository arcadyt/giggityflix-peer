from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MediaFile",
            fields=[
                (
                    "luid",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                (
                    "catalog_id",
                    models.CharField(blank=True, db_index=True, max_length=64, null=True),
                ),
                ("path", models.TextField()),
                ("relative_path", models.TextField(blank=True, null=True)),
                ("size_bytes", models.BigIntegerField()),
                (
                    "media_type",
                    models.CharField(
                        choices=[
                            ("video", "VIDEO"),
                            ("audio", "AUDIO"),
                            ("image", "IMAGE"),
                            ("unknown", "UNKNOWN"),
                        ],
                        default="unknown",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "PENDING"),
                            ("processing", "PROCESSING"),
                            ("ready", "READY"),
                            ("error", "ERROR"),
                            ("deleted", "DELETED"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(blank=True, null=True)),
                ("last_accessed", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.FloatField(blank=True, null=True)),
                ("width", models.IntegerField(blank=True, null=True)),
                ("height", models.IntegerField(blank=True, null=True)),
                ("codec", models.CharField(blank=True, max_length=64, null=True)),
                ("bitrate", models.IntegerField(blank=True, null=True)),
                ("framerate", models.FloatField(blank=True, null=True)),
                ("view_count", models.IntegerField(default=0)),
                ("last_viewed", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="Screenshot",
            fields=[
                (
                    "id",
                    models.CharField(max_length=64, primary_key=True, serialize=False),
                ),
                ("path", models.TextField()),
                ("timestamp", models.FloatField()),
                ("width", models.IntegerField()),
                ("height", models.IntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "media",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="screenshots",
                        to="media.mediafile",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MediaHash",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("algorithm", models.CharField(max_length=32)),
                ("hash_value", models.CharField(max_length=128)),
                (
                    "media",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="hashes",
                        to="media.mediafile",
                    ),
                ),
            ],
            options={
                "unique_together": {("media", "algorithm")},
            },
        ),
        migrations.AddIndex(
            model_name="mediafile",
            index=models.Index(fields=["media_type"], name="media_media_media_t_1c3f21_idx"),
        ),
        migrations.AddIndex(
            model_name="mediafile",
            index=models.Index(fields=["status"], name="media_media_status_7c6dac_idx"),
        ),
    ]
