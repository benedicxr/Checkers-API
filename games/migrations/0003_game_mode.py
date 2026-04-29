from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("games", "0002_moveentry_path_and_captured_positions"),
    ]

    operations = [
        migrations.AddField(
            model_name="game",
            name="mode",
            field=models.CharField(
                choices=[("vs_ai", "Vs AI"), ("pvp", "Player vs Player")],
                default="vs_ai",
                max_length=10,
            ),
        ),
    ]
