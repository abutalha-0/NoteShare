from django.db import migrations


def backfill_profiles(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    Profile = apps.get_model('profiles', 'Profile')
    database = schema_editor.connection.alias
    batch = []
    for user_id in User.objects.using(database).values_list('id', flat=True).iterator(chunk_size=500):
        batch.append(Profile(user_id=user_id))
        if len(batch) == 500:
            Profile.objects.using(database).bulk_create(batch, ignore_conflicts=True)
            batch.clear()
    if batch:
        Profile.objects.using(database).bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ('profiles', '0001_initial'),
    ]

    operations = [migrations.RunPython(backfill_profiles, migrations.RunPython.noop)]
