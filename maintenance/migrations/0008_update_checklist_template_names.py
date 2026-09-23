from django.db import migrations

def update_template_names(apps, schema_editor):
    ChecklistTemplate = apps.get_model('maintenance', 'ChecklistTemplate')
    ChecklistTemplate.objects.filter(code='STANDARD').update(name='قائمة الصيانة الدورية لماكينات الحقن والمكابس')
    ChecklistTemplate.objects.filter(code='SPRING').update(name='قائمة الصيانة الدورية لماكينات النفخ')

def reverse_template_names(apps, schema_editor):
    ChecklistTemplate = apps.get_model('maintenance', 'ChecklistTemplate')
    ChecklistTemplate.objects.filter(code='STANDARD').update(name='قائمة فحص المكن العادي والمكابس')
    ChecklistTemplate.objects.filter(code='SPRING').update(name='قائمة فحص مكن السوستة')

class Migration(migrations.Migration):

    dependencies = [
        ('maintenance', '0007_alter_factorymaintenancestate_current_asset_and_more'),
    ]

    operations = [
        migrations.RunPython(update_template_names, reverse_template_names),
    ]
