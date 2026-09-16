from django.contrib import admin

from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("body", "trip", "author", "kind", "is_pinned", "created_at")
    list_filter = ("kind", "is_pinned", "trip")
    list_editable = ("is_pinned",)
    actions = ("pin", "unpin")

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial.setdefault("kind", Post.Kind.ANNOUNCEMENT)
        return initial

    @admin.action(description="Pin selected posts")
    def pin(self, request, queryset):
        queryset.update(is_pinned=True)

    @admin.action(description="Unpin selected posts")
    def unpin(self, request, queryset):
        queryset.update(is_pinned=False)
