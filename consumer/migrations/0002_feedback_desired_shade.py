from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("consumer", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="feedback", name="desired_color_family",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="feedback", name="desired_finish",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
