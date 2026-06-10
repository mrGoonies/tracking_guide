from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('guides', '0011_guidestagephoto_pdf_backup'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeletedGuideNumber',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_guia', models.CharField(max_length=100, unique=True)),
                ('fecha_eliminacion', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Número de guía eliminada',
                'verbose_name_plural': 'Números de guías eliminadas',
                'ordering': ['-fecha_eliminacion'],
            },
        ),
    ]
