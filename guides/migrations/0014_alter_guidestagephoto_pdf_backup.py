from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('guides', '0013_seller_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='guidestagephoto',
            name='pdf_backup',
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
