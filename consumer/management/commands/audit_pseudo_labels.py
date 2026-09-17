"""Offline smoke test for synthetic portraits; never a real-world accuracy test."""

import csv
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from services.local_vision import (
    LocalVisionError, analyze_photo_local, create_face_landmarker, model_available,
)


DATA_DIR = Path(settings.BASE_DIR) / "data" / "pseudo-labels-tone"
REPORT_PATH = Path(settings.BASE_DIR) / "output" / "pseudo_label_smoke_test.csv"
REPORT_FIELDS = [
    "sample_id", "image_file", "source_skin_tone", "source_undertone_metadata",
    "lip_pseudo_label", "quality_flag", "pseudo_label_note", "analysis_status",
    "app_skin_tone", "app_undertone", "app_lip_pigmentation", "app_confidence",
    "skin_L", "skin_a", "skin_b", "lip_L", "lip_a", "lip_b",
    "app_analysis_note", "error",
]


def _analyze_row(annotation, data_root, landmarker):
    image_path = (DATA_DIR / annotation["image_file"]).resolve()
    if not image_path.is_relative_to(data_root):
        raise CommandError("image_file harus berada dalam folder pseudo-labels-tone.")
    row = {
        "sample_id": annotation["sample_id"],
        "image_file": annotation["image_file"],
        "source_skin_tone": annotation["skin_tone"],
        "source_undertone_metadata": annotation["undertone"],
        "lip_pseudo_label": annotation["pigmentasi_bibir"],
        "quality_flag": annotation["quality_flag"],
        "pseudo_label_note": annotation["catatan"],
        "analysis_status": "",
        "app_skin_tone": "", "app_undertone": "", "app_lip_pigmentation": "",
        "app_confidence": "", "skin_L": "", "skin_a": "", "skin_b": "",
        "lip_L": "", "lip_a": "", "lip_b": "",
        "app_analysis_note": "", "error": "",
    }
    try:
        profile = analyze_photo_local(image_path.read_bytes(), "image/jpeg",
                                      face_landmarker=landmarker)
    except (LocalVisionError, OSError) as error:
        row["analysis_status"] = "not_analyzed"
        row["error"] = str(error)
    except Exception as error:
        # Preserve the remaining rows and expose unexpected failures for debugging.
        row["analysis_status"] = "unexpected_error"
        row["error"] = f"{type(error).__name__}: {error}"
    else:
        row["analysis_status"] = "analyzed"
        row["app_skin_tone"] = profile.get("skin_tone", "")
        row["app_undertone"] = profile.get("undertone", "")
        row["app_lip_pigmentation"] = profile.get("lip_pigmentation", "")
        row["app_confidence"] = profile.get("confidence", "")
        row["app_analysis_note"] = profile.get("analysis_note", "")
        measurement = profile.get("measurement") or {}
        for prefix in ("skin", "lip"):
            values = measurement.get(f"{prefix}_lab") or ()
            if len(values) == 3:
                for channel, value in zip(("L", "a", "b"), values):
                    row[f"{prefix}_{channel}"] = value
    return row


class Command(BaseCommand):
    help = "Uji pipeline analisis lokal pada 30 potret sintetis dan simpan perbandingan untuk ditinjau, bukan skor akurasi."

    def handle(self, *args, **options):
        annotation_path = DATA_DIR / "annotations.csv"
        if not annotation_path.is_file():
            raise CommandError("annotations.csv untuk pseudo-label sintetis tidak ditemukan.")
        with annotation_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            required = {"sample_id", "image_file", "skin_tone", "undertone",
                        "pigmentasi_bibir", "quality_flag", "catatan"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise CommandError("Kolom wajib pada annotations.csv tidak lengkap.")
            annotations = list(reader)

        if not annotations:
            raise CommandError("annotations.csv tidak berisi sampel.")
        if not model_available():
            raise CommandError("Model Face Landmarker lokal belum tersedia.")
        data_root = DATA_DIR.resolve()
        try:
            with create_face_landmarker() as landmarker:
                report = [_analyze_row(annotation, data_root, landmarker)
                          for annotation in annotations]
        except (OSError, RuntimeError, ValueError) as error:
            raise CommandError("Model deteksi wajah lokal gagal dibuka.") from error

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with REPORT_PATH.open("w", encoding="utf-8-sig", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=REPORT_FIELDS)
            writer.writeheader()
            writer.writerows(report)

        statuses = Counter(row["analysis_status"] for row in report)
        estimates = sum(row["app_confidence"] == "local_estimate" for row in report)
        self.stdout.write(f"Sampel sintetis: {len(report)}; dianalisis: {statuses['analyzed']}; "
                          f"estimasi warna: {estimates}; gagal: {statuses['not_analyzed']}; "
                          f"error tak terduga: {statuses['unexpected_error']}.")
        self.stdout.write(f"Laporan per gambar: {REPORT_PATH}")
        self.stdout.write("Bandingkan kolom secara manual. Ini bukan uji akurasi; undertone sumber "
                          "tidak dikondisikan pada gambar sintetis.")
