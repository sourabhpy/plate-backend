from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="username",
            field=models.CharField(db_index=True, default="user", max_length=150, unique=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="user",
            name="name",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
