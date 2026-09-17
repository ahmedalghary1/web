import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from factories.models import Factory
from assets.models import Asset
from maintenance.models import ChecklistTemplate, ChecklistSection, ChecklistItem

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Seeds the database with standard factories, assets, and checklists."

    def handle(self, *args, **options):
        with transaction.atomic():
            self.seed_checklists()
            self.seed_factories_and_assets()
        self.stdout.write(self.style.SUCCESS('Successfully seeded all factory data!'))

    def seed_checklists(self):
        # 1. STANDARD Template (F1, F3, and Regular machines in F2)
        std_tpl, _ = ChecklistTemplate.objects.get_or_create(code="STANDARD", defaults={"name": "فحص الماكينات والمكابس", "version": 1, "is_active": True})
        
        std_sections = [
            ("الموتور", [
                "عدم وجود صوت غير طبيعي أو إهتزاز",
                "درجة الحرارة",
                "سلامة الكابلات",
                "نظافة الموتور من الأتربة"
            ]),
            ("طلمبة الزيت", [
                "مستوي الزيت في الخزان",
                "لون الزيت",
                "عدم وجود تسريب زيت من الوصلات",
                "عدم وجود صوت غير طبيعي او اهتزاز"
            ]),
            ("دائرة الهيدروليك", [
                "نظافة الفلاتر وعدم انسدادها",
                "فحص الخراطيم والوصلات",
                "فحص البلوف",
                "قياس ضغط الهيدروليك"
            ]),
            ("دائرة التبريد", [
                "دخول وخروج المياة بشكل صحيح",
                "نظافة الفلاتر وعدم انسدادها"
            ]),
            ("وحده الحقن", [
                "سلامة موتور الاسكرو",
                "فحص البريمة والتأكد من عدم وجود تآكل"
            ]),
            ("الكهرباء", [
                "فحص لوحة التحكم",
                "تثبيت الاسلاك بشكل جيد",
                "التاكد من فيوزات الامان",
                "التاكد من عدم وجود خطا بشاشة الكنترول",
                "اختبار الامان الكهربي"
            ]),
            ("الامان", [
                "اختبار فتح وغلق الابواب",
                "اختبار مفاتيح الامان",
                "اختبار الامان الميكانيكي"
            ])
        ]
        
        for s_idx, (sec_name, items) in enumerate(std_sections, 1):
            sec, _ = ChecklistSection.objects.update_or_create(template=std_tpl, sequence_order=s_idx, defaults={"name": sec_name})
            for i_idx, text in enumerate(items, 1):
                ChecklistItem.objects.update_or_create(section=sec, sequence_order=i_idx, defaults={"text": text})
                
        # 2. SPRING Template (Spring machines in F2)
        spr_tpl, _ = ChecklistTemplate.objects.get_or_create(code="SPRING", defaults={"name": "فحص ماكينات السوستة", "version": 1, "is_active": True})
        
        spr_sections = [
            ("الموتور", [
                "عدم وجود صوت غير طبيعي او اهتزاز",
                "درجة الحرارة",
                "سلامة الكابلات",
                "نظافة الموتور من الاتربة"
            ]),
            ("الجير بوكس", [
                "تاكد من مستوي الزيت",
                "لون ورائحة الزيت",
                "عدم وجود تسريب زيت",
                "لف العمود بيديك للتاكد من سلامة الحركة"
            ]),
            ("القم", [
                "التشحييم والتزييت",
                "الغسيل اذا كان هناك صدا",
                "فحص برس اللقم"
            ]),
            ("النظام الكهربي", [
                "فحص جميع الاسلاك والتاكد من سلامة التوصيلات",
                "فحص جميع الفيوزات والكونتاكتورات",
                "فحص السخانات وتنظيف سطحها",
                "فحص الحساسات الحرارية"
            ])
        ]
        
        for s_idx, (sec_name, items) in enumerate(spr_sections, 1):
            sec, _ = ChecklistSection.objects.update_or_create(template=spr_tpl, sequence_order=s_idx, defaults={"name": sec_name})
            for i_idx, text in enumerate(items, 1):
                ChecklistItem.objects.update_or_create(section=sec, sequence_order=i_idx, defaults={"text": text})

    def seed_factories_and_assets(self):
        f1, _ = Factory.objects.get_or_create(code="F1", defaults={"name": "مصنع 1"})
        f2, _ = Factory.objects.get_or_create(code="F2", defaults={"name": "مصنع 2"})
        f3, _ = Factory.objects.get_or_create(code="F3", defaults={"name": "مصنع 3"})

        def add_assets(factory, regular_count, press_count, spring_count):
            seq = 1
            for i in range(1, regular_count + 1):
                Asset.objects.get_or_create(factory=factory, asset_code=f"M-{i}", defaults={"asset_type": Asset.Type.REGULAR_MACHINE, "sequence_order": seq})
                seq += 1
            for i in range(1, press_count + 1):
                Asset.objects.get_or_create(factory=factory, asset_code=f"P-{i}", defaults={"asset_type": Asset.Type.PRESS, "sequence_order": seq})
                seq += 1
            for i in range(1, spring_count + 1):
                Asset.objects.get_or_create(factory=factory, asset_code=f"S-{i}", defaults={"asset_type": Asset.Type.SPRING_MACHINE, "sequence_order": seq})
                seq += 1
        
        # Factory 1: 17 machines, 5 presses
        add_assets(f1, 17, 5, 0)
        # Factory 3: 17 machines, 5 presses
        add_assets(f3, 17, 5, 0)
        # Factory 2: 17 machines, 5 spring machines (as assumed)
        add_assets(f2, 17, 0, 5)
