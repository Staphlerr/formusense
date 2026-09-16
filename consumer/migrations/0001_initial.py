from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.CreateModel(
        name="Feedback",
        fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("shade_id", models.CharField(max_length=12)),
            ("shade_name", models.CharField(max_length=100)),
            ("region", models.CharField(blank=True, max_length=50)),
            ("skin_tone", models.CharField(blank=True, max_length=30)),
            ("undertone", models.CharField(blank=True, max_length=30)),
            ("lip_pigmentation", models.CharField(blank=True, max_length=30)),
            ("feedback_type", models.CharField(choices=[("color_interest", "Ketertarikan warna"), ("wear_feedback", "Pengalaman pemakaian")], max_length=20)),
            ("color_response", models.CharField(blank=True, max_length=40)),
            ("texture_response", models.CharField(blank=True, max_length=40)),
            ("finish_response", models.CharField(blank=True, max_length=40)),
            ("rating", models.PositiveSmallIntegerField(blank=True, null=True)),
            ("comment", models.TextField(blank=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ],
    )]
