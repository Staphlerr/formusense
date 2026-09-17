from django.db import migrations


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.using(schema_editor.connection.alias).get_or_create(name="consumer")
    Group.objects.using(schema_editor.connection.alias).get_or_create(name="rd")


class Migration(migrations.Migration):
    dependencies = [("auth", "0012_alter_user_first_name_max_length")]
    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
