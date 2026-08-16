from django.contrib import admin

from devices.models import Device, Payload


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("devEUI", "status", "audit_created_at", "audit_modified_at")
    search_fields = ("devEUI",)
    readonly_fields = ("audit_created_at", "audit_modified_at")


@admin.register(Payload)
class PayloadAdmin(admin.ModelAdmin):
    list_display = ("device", "fCnt", "data", "status", "audit_created_at")
    list_filter = ("status",)
    search_fields = ("device__devEUI",)
    readonly_fields = ("audit_created_at", "audit_modified_at", "raw_payload")
