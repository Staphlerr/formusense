"""Generate a review brief from an opportunity and observed feedback."""

from collections import Counter

from services.analytics import opportunities, signals
from services.data import read_demo_csv


VALIDATION_STEPS = [
    "Periksa identitas, izin, dan batas pemakaian setiap bahan",
    "Buat beberapa batch percobaan dengan variasi rasio pigmen",
    "Uji drawdown warna dan payoff pada beberapa warna bibir",
    "Uji stabilitas, tekstur, dan kenyamanan pemakaian",
    "Lakukan uji kesukaan konsumen sebelum keputusan produk",
]


def build_formula_brief(opportunity_id):
    item = next((row for row in opportunities() if row["opportunity_id"] == opportunity_id), None)
    if item is None:
        raise ValueError("Peluang tidak ditemukan")

    related = [row for row in signals() if row["color_family"] == item["family"]
               or row["desired_color_family"] == item["family"]]
    issues = Counter()
    for row in related:
        if row["feedback_type"] != "wear_feedback":
            continue
        for field in ("color_response", "texture_response", "finish_response"):
            value = row[field]
            if value.startswith("too_"):
                issues[value] += 1

    if item["family"] == "terracotta":
        pigment_direction = [
            "Eksplorasi arah merah-cokelat hangat; uji keseimbangan red oxide dan yellow oxide.",
            "Bandingkan tingkat kecerahan agar warna tidak tampak pucat pada bibir berpigmen.",
            "Tetapkan tingkat pigmen melalui drawdown dan payoff test, bukan dari prediksi layar saja.",
        ]
    else:
        pigment_direction = [
            "Eksplorasi keluarga mauve-rose dengan beberapa tingkat kedalaman dan saturasi.",
            "Bandingkan hasil warna pada profil warm/olive agar tidak tampak kusam.",
            "Tetapkan rasio pigmen setelah pengukuran warna dan uji drawdown.",
        ]

    if item["preferred_finish"] == "glossy":
        base_direction = "Uji basis glossy dan keseimbangan oil/binder sambil mengamati rasa lengket."
    elif item["preferred_finish"] == "satin":
        base_direction = "Mulai dari basis satin contoh; evaluasi slip, kenyamanan, dan payoff."
    else:
        base_direction = f"Uji basis dengan finish {item['preferred_finish']} dan nilai kenyamanannya."

    top_issue = issues.most_common(1)[0][0].replace("_", " ") if issues else None
    example = next((row for row in read_demo_csv("formula_draft_demo.csv")
                    if row["opportunity_id"] == opportunity_id), None)
    return {"brief": {
        "opportunity": item,
        "pigment_direction": pigment_direction,
        "base_direction": base_direction,
        "top_issue": top_issue,
        "issues_sample": sum(issues.values()),
        "validation_steps": VALIDATION_STEPS,
        "illustrative_composition": example,
    }}
