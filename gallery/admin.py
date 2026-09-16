from django.contrib import admin
from django.utils.html import format_html

from .models import Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("preview", "trip", "uploaded_by", "caption", "created_at")
    list_filter = ("trip",)

    @admin.display(description="preview")
    def preview(self, obj):
        if not obj.image:
            return "—"
        return format_html(
            '<img src="{}" style="height:48px;border-radius:4px">', obj.image.url
        )
