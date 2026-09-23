from django.core.management.base import BaseCommand
from factories.models import Factory
from assets.models import Asset
from accounts.models import User
from production.models import Product, MachineOperator, MachineProductionDefault

class Command(BaseCommand):
    help = "Seed initial production data (products, operators, and machine defaults)"

    def handle(self, *args, **options):
        # 1. Seed demo production supervisors if not exist
        f1 = Factory.objects.filter(code="F1").first()
        f2 = Factory.objects.filter(code="F2").first()
        f3 = Factory.objects.filter(code="F3").first()

        if f1:
            u1, created = User.objects.get_or_create(
                phone="01111111111",
                defaults={"name": "أحمد محمود (مشرف إنتاج مصنع 1)", "role": User.Role.PRODUCTION_SUPERVISOR, "factory": f1}
            )
            if created:
                u1.set_password("ElwsamProd@123")
                u1.save()

            u2, created = User.objects.get_or_create(
                phone="01111111112",
                defaults={"name": "محمد حسن (مشرف وردية ثانية مصنع 1)", "role": User.Role.PRODUCTION_SUPERVISOR, "factory": f1}
            )
            if created:
                u2.set_password("ElwsamProd@123")
                u2.save()

        # 2. Seed common products for each factory
        products_data = [
            ("غطاء برطمان 100 مم", "PRD-CAP-100", 18.5),
            ("غطاء برطمان 120 مم", "PRD-CAP-120", 24.0),
            ("شماعة ملابس أطفال", "PRD-HANGER-CH", 35.0),
            ("شماعة ملابس رجالي", "PRD-HANGER-AD", 52.0),
            ("يد جردل بلاستيك", "PRD-HANDLE-BKT", 15.0),
            ("طبة بستم 2 بوصة", "PRD-PLUG-02", 42.0),
        ]

        for factory in Factory.objects.all():
            for name, code, wt in products_data:
                Product.objects.get_or_create(
                    factory=factory,
                    name=name,
                    defaults={"code": f"{factory.code}-{code}", "weight_per_piece_grams": wt, "is_active": True}
                )

        # 3. Seed operators for each factory
        operators_data = ["إبراهيم السيد", "محمود عبد العال", "صلاح مصطفى", "علي فرج", "رمضان خليل", "فتحي عثمان"]
        for factory in Factory.objects.all():
            for name in operators_data:
                MachineOperator.objects.get_or_create(
                    factory=factory,
                    name=f"{name} ({factory.name})",
                    defaults={"is_active": True}
                )

        # 4. Seed machine production defaults for all active assets
        for asset in Asset.objects.filter(is_active=True, is_archived=False):
            prod = Product.objects.filter(factory=asset.factory, is_active=True).first()
            MachineProductionDefault.objects.get_or_create(
                asset=asset,
                defaults={
                    "default_product": prod,
                    "original_cavities": 8 if asset.asset_type == Asset.Type.REGULAR_MACHINE else (4 if asset.asset_type == Asset.Type.SPRING_MACHINE else 1),
                    "cooling_time_seconds": 12.5,
                    "cycle_time_seconds": 22.0,
                    "target_cycle_production": 450.0
                }
            )

        self.stdout.write(self.style.SUCCESS("Successfully seeded production reference data!"))
