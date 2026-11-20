from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('guides', '0014_alter_guidestagephoto_pdf_backup'),
    ]

    operations = [
        migrations.AddField(
            model_name='guidestage',
            name='operation_id',
            field=models.UUIDField(
                blank=True,
                editable=False,
                help_text='Identificador idempotente del cambio de estado.',
                null=True,
                unique=True,
            ),
        ),
    ]
