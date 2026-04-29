from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="moveentry",
            name="captured_positions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="moveentry",
            name="path",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
