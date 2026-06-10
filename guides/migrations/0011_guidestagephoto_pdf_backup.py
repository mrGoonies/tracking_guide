import guides.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('guides', '0010_fix_photo_field_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='guidestagephoto',
            name='pdf_backup',
            field=models.FileField(
                blank=True,
                max_length=500,
                null=True,
                storage=guides.models._pdf_storage,
                upload_to=guides.models._guide_pdf_path,
            ),
        ),
    ]
