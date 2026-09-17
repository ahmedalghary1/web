from django.contrib import admin
from maintenance.models import ChecklistItem, ChecklistSection, ChecklistTemplate, FactoryMaintenanceState, MaintenanceReport, MaintenanceReportItem
admin.site.register([ChecklistTemplate, ChecklistSection, ChecklistItem, FactoryMaintenanceState, MaintenanceReport, MaintenanceReportItem])
