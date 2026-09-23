from django.contrib import admin
from maintenance.models import ChecklistItem, ChecklistSection, ChecklistTemplate, FactoryMaintenanceState, MaintenanceReport, MaintenanceReportItem, EmergencyMaintenanceItem
admin.site.register([ChecklistTemplate, ChecklistSection, ChecklistItem, FactoryMaintenanceState, MaintenanceReport, MaintenanceReportItem, EmergencyMaintenanceItem])
