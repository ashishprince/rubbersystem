from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_block_minimum_daily_yield_wagerecord'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketPrice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('price_per_kg', models.FloatField(help_text='RSS4 rubber price in ₹ per kg')),
                ('source', models.CharField(default='Rubber Board India', max_length=200)),
                ('fetched_at', models.DateTimeField(auto_now_add=True)),
                ('fetch_type', models.CharField(
                    choices=[('AUTO', 'Automatic'), ('MANUAL', 'Manual')],
                    default='AUTO', max_length=10
                )),
                ('is_active', models.BooleanField(default=True, help_text='Only the latest record is active')),
            ],
            options={
                'ordering': ['-fetched_at'],
            },
        ),
    ]
