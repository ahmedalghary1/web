from django.db import migrations

FACTORIES = [("F1", "مصنع 1"), ("F2", "مصنع 2"), ("F3", "مصنع 3")]
STANDARD = [
    ("الموتور", ["عدم وجود صوت غير طبيعي أو إهتزاز", "درجة الحرارة", "سلامة الكابلات", "نظافة الموتور من الأتربة"]),
    ("طلمبة الزيت", ["مستوي الزيت في الخزان", "لون الزيت", "عدم وجود تسريب زيت من الوصلات", "عدم وجود صوت غير طبيعي او اهتزاز"]),
    ("دائرة الهيدروليك", ["نظافة الفلاتر وعدم انسدادها", "فحص الخراطيم والوصلات", "فحص البلوف", "قياس ضغط الهيدروليك"]),
    ("دائرة التبريد", ["دخول وخروج المياة بشكل صحيح", "نظافة الفلاتر وعدم انسدادها"]),
    ("وحدة الحقن", ["سلامة موتور الاسكرو", "فحص البريمة والتأكد من عدم وجود تآكل"]),
    ("الكهرباء", ["فحص لوحة التحكم", "تثبيت الاسلاك بشكل جيد", "التاكد من فيوزات الامان", "التاكد من عدم وجود خطا بشاشة الكنترول", "اختبار الامان الكهربي"]),
    ("الامان", ["اختبار فتح وغلق الابواب", "اختبار مفاتيح الامان", "اختبار الامان الميكانيكي"]),
]
SPRING = [
    ("الموتور", ["عدم وجود صوت غير طبيعي او اهتزاز", "درجة الحرارة", "سلامة الكابلات", "نظافة الموتور من الاتربة"]),
    ("الجير بوكس", ["تاكد من مستوي الزيت", "لون ورائحة الزيت", "عدم وجود تسريب زيت", "لف العمود بيديك للتاكد من سلامة الحركة"]),
    ("اللقم", ["التشحييم والتزييت", "الغسيل اذا كان هناك صدا", "فحص برس اللقم"]),
    ("النظام الكهربي", ["فحص جميع الاسلاك والتاكد من سلامة التوصيلات", "فحص جميع الفيوزات والكونتاكتورات", "فحص السخانات وتنظيف سطحها", "فحص الحساسات الحرارية"]),
]

def seed(apps, schema_editor):
    Factory = apps.get_model("factories", "Factory"); Template = apps.get_model("maintenance", "ChecklistTemplate"); Section = apps.get_model("maintenance", "ChecklistSection"); Item = apps.get_model("maintenance", "ChecklistItem")
    for code, name in FACTORIES: Factory.objects.update_or_create(code=code, defaults={"name": name, "is_active": True})
    for code, name, sections in [("STANDARD", "قائمة فحص المكن العادي والمكابس", STANDARD), ("SPRING", "قائمة فحص مكن السوستة", SPRING)]:
        template, _ = Template.objects.update_or_create(code=code, defaults={"name": name, "version": 1, "is_active": True})
        for section_order, (section_name, items) in enumerate(sections, 1):
            section, _ = Section.objects.update_or_create(template=template, sequence_order=section_order, defaults={"name": section_name})
            for item_order, text in enumerate(items, 1): Item.objects.update_or_create(section=section, sequence_order=item_order, defaults={"text": text, "is_active": True})

def unseed(apps, schema_editor):
    apps.get_model("maintenance", "ChecklistTemplate").objects.filter(code__in=["STANDARD", "SPRING"]).delete()
    apps.get_model("factories", "Factory").objects.filter(code__in=["F1", "F2", "F3"]).delete()

class Migration(migrations.Migration):
    dependencies = [("maintenance", "0001_initial"), ("factories", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
