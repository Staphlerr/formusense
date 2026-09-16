"""Check Sumopod credentials and configured model IDs without logging the key."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Periksa apakah API key dan model AI pada .env dikenali oleh endpoint /models."

    def handle(self, *args, **options):
        api_key = os.environ.get("AI_API_KEY", "")
        if not api_key:
            raise CommandError("AI_API_KEY belum diisi. Edit file .env di folder utama proyek.")
        base_url = os.environ.get("AI_BASE_URL", "https://ai.sumopod.com/v1").rstrip("/")
        if not base_url.startswith("https://"):
            raise CommandError("AI_BASE_URL harus memakai HTTPS.")
        request = Request(f"{base_url}/models", headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urlopen(request, timeout=15) as response:
                payload = json.load(response)
        except HTTPError as error:
            raise CommandError(f"API menolak permintaan (HTTP {error.code}). Periksa key dan base URL.") from None
        except (URLError, OSError, ValueError) as error:
            raise CommandError("Endpoint model tidak dapat diakses. Periksa koneksi/base URL atau lihat dashboard Sumopod.") from error
        models = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            raise CommandError("Respons /models tidak berisi daftar model. Cek ID di dashboard Sumopod.")
        available = {item.get("id") for item in models if isinstance(item, dict)}
        self.stdout.write(self.style.SUCCESS("API key diterima oleh endpoint daftar model."))
        for variable in ("AI_VISION_MODEL", "AI_TEXT_MODEL"):
            model = os.environ.get(variable, "")
            if not model:
                self.stdout.write(self.style.WARNING(f"{variable} belum diisi."))
            elif model in available:
                self.stdout.write(self.style.SUCCESS(f"{variable}={model} ditemukan."))
            else:
                self.stdout.write(self.style.WARNING(f"{variable}={model} tidak ada di daftar. Cek ID pada dashboard."))
        self.stdout.write("Catatan: /models hanya memastikan ID tersedia; kemampuan membaca gambar perlu dicoba terpisah.")
