from django import forms

from consumer.models import Feedback


class ProfileStartForm(forms.Form):
    nickname = forms.CharField(label="Nama panggilan", max_length=50, required=False)
    age_range = forms.ChoiceField(label="Rentang usia", choices=[
        ("", "Pilih (opsional)"), ("under_18", "Di bawah 18"),
        ("18_24", "18–24"), ("25_34", "25–34"), ("35_plus", "35+"),
    ], required=False)
    region = forms.ChoiceField(label="Wilayah", choices=[
        ("", "Pilih (opsional)"), ("Jakarta", "Jakarta"),
        ("West Java", "Jawa Barat"), ("Central Java", "Jawa Tengah"),
        ("East Java", "Jawa Timur"), ("Sumatra", "Sumatra"),
        ("Kalimantan", "Kalimantan"), ("Sulawesi", "Sulawesi"),
        ("Bali & Nusa Tenggara", "Bali & Nusa Tenggara"), ("Papua", "Papua"),
    ], required=False)


# Choices below match services/data.py's real 30-shade catalog
# (color_family / finish values, lowercased from the team's
# Shade_Catalog.csv), not the old 24-row demo catalog's vocabulary --
# so every option a wearer can pick here actually exists among the real
# shades services.recommendation.recommend() scores against. The old demo
# catalog additionally had coral/terracotta/berry/mauve color families and
# satin/cream finishes, none of which appear in the real catalog; offering
# them here would let someone "prefer" a color/finish combination no real
# shade can ever match.
class PreferenceForm(forms.Form):
    color = forms.ChoiceField(label="Warna yang disukai", choices=[
        ("", "Belum tahu"), ("nude", "Nude"), ("pink", "Pink"),
        ("orange", "Orange"), ("peach", "Peach"),
        ("red", "Merah"), ("brown", "Cokelat"),
    ], required=False)
    finish = forms.ChoiceField(label="Hasil akhir", choices=[
        ("", "Belum tahu"), ("matte", "Matte"),
        ("glossy", "Glossy"), ("glasting", "Glasting"),
    ], required=False)
    intensity = forms.ChoiceField(label="Kesan", choices=[
        ("", "Belum tahu"), ("natural", "Natural"),
        ("medium", "Segar"), ("bold", "Berani"),
    ], required=False)


class LipProfileForm(forms.Form):
    skin_tone = forms.ChoiceField(label="Warna kulit", choices=[
        ("light", "Light"), ("light_medium", "Light Medium"),
        ("medium", "Medium"), ("tan", "Tan"), ("deep", "Deep"),
        ("uncertain", "Belum yakin"),
    ])
    undertone = forms.ChoiceField(label="Undertone", choices=[
        ("warm", "Warm"), ("cool", "Cool"),
        ("neutral", "Neutral"), ("olive", "Olive"),
        ("uncertain", "Belum yakin"),
    ])
    lip_pigmentation = forms.ChoiceField(label="Pigmentasi bibir", choices=[
        ("low", "Low"), ("medium", "Medium"),
        ("medium_high", "Medium–High"), ("high", "High"),
        ("uncertain", "Belum yakin"),
    ])
    visible_lip_condition = forms.CharField(label="Ciri bibir yang terlihat", max_length=120, required=False)


class FeedbackForm(forms.ModelForm):
    rd_consent = forms.BooleanField(
        label="Saya setuju feedback dan profil warna saya disimpan untuk analisis R&D demo.",
        required=True,
    )
    desired_color_family = forms.ChoiceField(
        label="Warna yang masih kamu cari", required=False,
        choices=[
            ("", "Tidak ada / belum tahu"), ("nude", "Nude"),
            ("pink", "Pink"), ("coral", "Coral"),
            ("terracotta", "Terracotta"), ("red", "Merah"),
            ("berry", "Berry"), ("mauve", "Mauve / rose"),
            ("brown", "Cokelat"),
        ],
    )
    desired_finish = forms.ChoiceField(
        label="Hasil akhir yang dicari", required=False,
        choices=[
            ("", "Tidak ada / belum tahu"), ("satin", "Satin"),
            ("matte", "Matte"), ("cream", "Cream"),
            ("glossy", "Glossy"),
        ],
    )
    rating = forms.TypedChoiceField(
        label="Rating setelah mencoba (1–5)", required=False, coerce=int, empty_value=None,
        choices=[("", "Belum memberi rating")] + [(n, str(n)) for n in range(1, 6)],
    )
    tried_product = forms.BooleanField(
        label="Saya benar-benar sudah mencoba produk ini",
        required=False,
    )

    class Meta:
        model = Feedback
        fields = ["feedback_type", "color_response", "texture_response",
                  "finish_response", "rating", "desired_color_family",
                  "desired_finish", "comment"]
        widgets = {
            "feedback_type": forms.RadioSelect,
            "color_response": forms.Select(choices=[
                ("", "Pilih"), ("love_it", "Suka sekali"),
                ("like_it", "Suka"), ("not_sure", "Belum yakin"),
                ("not_for_me", "Kurang cocok"), ("too_pale", "Terlalu pucat"),
                ("just_right", "Pas"), ("too_dark", "Terlalu gelap"),
            ]),
            "texture_response": forms.Select(choices=[
                ("", "Pilih (jika sudah mencoba)"), ("too_dry", "Terlalu kering"),
                ("comfortable", "Nyaman"), ("too_sticky", "Terlalu lengket"),
                ("too_thick", "Terlalu tebal"),
            ]),
            "finish_response": forms.Select(choices=[
                ("", "Pilih (jika sudah mencoba)"), ("too_matte", "Terlalu matte"),
                ("just_right", "Pas"), ("too_glossy", "Terlalu glossy"),
            ]),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "Opsional"}),
        }
        labels = {
            "feedback_type": "Jenis penilaian",
            "color_response": "Penilaian warna",
            "texture_response": "Tekstur",
            "finish_response": "Hasil akhir",
            "rating": "Rating setelah mencoba (1–5)",
            "comment": "Komentar",
        }

    def clean(self):
        data = super().clean()
        is_wear = data.get("feedback_type") == Feedback.WEAR
        if not data.get("color_response"):
            self.add_error("color_response", "Pilih penilaian warna.")
        if is_wear and not data.get("tried_product"):
            self.add_error("tried_product", "Pilih ini hanya jika produk sudah dicoba.")
        if not is_wear:
            data["texture_response"] = ""
            data["finish_response"] = ""
            data["rating"] = None
        return data