from django.db import migrations, models


def preserve_recorded_times(apps, schema_editor):
    # The historical report is the only reliable source; present-day machine
    # defaults may already have changed since that shift was recorded.
    Entry = apps.get_model("production", "MachineProductionEntry")
    Entry.objects.using(schema_editor.connection.alias).update(
        original_cooling_time_seconds=models.F("cooling_time_seconds"),
        original_cycle_time_seconds=models.F("cycle_time_seconds"),
    )


class Migration(migrations.Migration):
    dependencies = [("production", "0003_configurable_production_choices")]

    operations = [
        migrations.AddField(
            model_name="machineproductionentry",
            name="original_cooling_time_seconds",
            field=models.FloatField(default=0.0, verbose_name="التبريد الأصلي (ثانية)"),
        ),
        migrations.AddField(
            model_name="machineproductionentry",
            name="original_cycle_time_seconds",
            field=models.FloatField(default=0.0, verbose_name="الدورة الأصلية (ثانية)"),
        ),
        migrations.RunPython(preserve_recorded_times, migrations.RunPython.noop),
    ]
