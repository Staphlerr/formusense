from django.db import models


class Feedback(models.Model):
    INTEREST = "color_interest"
    WEAR = "wear_feedback"
    TYPE_CHOICES = [(INTEREST, "Ketertarikan warna"), (WEAR, "Pengalaman pemakaian")]

    shade_id = models.CharField(max_length=12)
    shade_name = models.CharField(max_length=100)
    region = models.CharField(max_length=50, blank=True)
    skin_tone = models.CharField(max_length=30, blank=True)
    undertone = models.CharField(max_length=30, blank=True)
    lip_pigmentation = models.CharField(max_length=30, blank=True)
    feedback_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    color_response = models.CharField(max_length=40, blank=True)
    texture_response = models.CharField(max_length=40, blank=True)
    finish_response = models.CharField(max_length=40, blank=True)
    desired_color_family = models.CharField(max_length=30, blank=True)
    desired_finish = models.CharField(max_length=20, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.shade_name}: {self.get_feedback_type_display()}"
