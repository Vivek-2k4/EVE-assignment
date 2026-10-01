from decimal import Decimal

from django.core.management.base import BaseCommand

from catalog.models import Centre, CentreTest, DiagnosticTest

TESTS = {
    "Complete Blood Count": "CBC panel",
    "Lipid Profile": "Cholesterol and triglycerides",
    "Thyroid Profile (T3, T4, TSH)": "Thyroid function",
    "HbA1c": "3-month average blood sugar",
}
CENTRES = {
    ("EVE Diagnostics Karol Bagh", "Delhi"): {"Complete Blood Count": "350", "Lipid Profile": "600", "HbA1c": "450"},
    ("EVE Diagnostics Indiranagar", "Bengaluru"): {"Complete Blood Count": "400", "Thyroid Profile (T3, T4, TSH)": "700"},
}


class Command(BaseCommand):
    help = "Seed a few centres/tests for local demos (idempotent)."

    def handle(self, *args, **options):
        tests = {n: DiagnosticTest.objects.get_or_create(name=n, defaults={"description": d})[0] for n, d in TESTS.items()}
        for (name, location), offers in CENTRES.items():
            centre, _ = Centre.objects.get_or_create(name=name, location=location)
            for test_name, price in offers.items():
                CentreTest.objects.update_or_create(
                    centre=centre, test=tests[test_name], defaults={"price": Decimal(price)}
                )
        self.stdout.write(self.style.SUCCESS("Seeded demo data."))
