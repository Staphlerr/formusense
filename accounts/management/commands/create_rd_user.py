from getpass import getpass

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.access import RESEARCH_GROUP


class Command(BaseCommand):
    help = "Buat akun R&D (password dimasukkan secara interaktif)."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        username = options["username"].strip()
        User = get_user_model()
        if not username:
            raise CommandError("Nama pengguna tidak boleh kosong.")
        if User.objects.filter(username=username).exists():
            raise CommandError("Nama pengguna sudah dipakai. Pilih nama lain.")
        password = getpass("Password R&D: ")
        repeat = getpass("Ulangi password: ")
        if password != repeat:
            raise CommandError("Password tidak sama.")
        try:
            password_validation.validate_password(password)
        except ValidationError as error:
            raise CommandError(str(error)) from error
        with transaction.atomic():
            user = User.objects.create_user(username=username, password=password)
            group, _ = Group.objects.get_or_create(name=RESEARCH_GROUP)
            user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(f"Akun R&D {username} dibuat."))
