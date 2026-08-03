from django.contrib import admin

from .models import Event
from .models import SpecialLotteryGroup
from .models import SpecialLotterySettlement


class SpecialLotteryEventInline(admin.TabularInline):
    model = Event
    fields = ("title", "start_date", "end_date", "special_lottery_order")
    extra = 0


@admin.register(SpecialLotteryGroup)
class SpecialLotteryGroupAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "draw_mode",
        "is_drawn",
        "is_finalized",
        "created_at",
        "finalized_at",
    )
    list_filter = ("draw_mode", "is_drawn", "is_finalized")
    search_fields = ("name", "description")
    inlines = (SpecialLotteryEventInline,)
    readonly_fields = (
        "name",
        "description",
        "draw_mode",
        "is_drawn",
        "is_finalized",
        "created_at",
        "finalized_at",
        "finalized_by",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SpecialLotterySettlement)
class SpecialLotterySettlementAdmin(admin.ModelAdmin):
    list_display = (
        "group",
        "participant",
        "application_count",
        "selected_count",
        "previous_weight",
        "new_weight",
        "adjustment",
    )
    list_filter = ("group", "adjustment")
    search_fields = (
        "group__name",
        "participant__name",
        "participant__username",
    )
    readonly_fields = (
        "group",
        "participant",
        "application_count",
        "selected_count",
        "total_application_count",
        "total_selected_count",
        "previous_weight",
        "new_weight",
        "adjustment",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def has_delete_permission(self, request, obj=None):
        return False
