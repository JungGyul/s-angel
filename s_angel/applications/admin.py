from django.contrib import admin

from .models import WeightChange
from .models import BudgetYear
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
    list_select_related = ("group", "participant")
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


@admin.register(BudgetYear)
class BudgetYearAdmin(admin.ModelAdmin):
    list_display = ("year", "is_active", "reason", "created_at", "created_by")
    list_filter = ("is_active",)
    search_fields = ("reason", "created_by__username", "created_by__name")
    list_select_related = ("created_by",)
    readonly_fields = ("created_at", "created_by")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "reason":
            kwargs["required"] = True
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WeightChange)
class WeightChangeAdmin(admin.ModelAdmin):
    list_display = ('user', 'source', 'source_id', 'before', 'after', 'created_at', 'created_by')
    list_filter = ('source', 'created_at')
    list_select_related = ('user', 'created_by')
    search_fields = ('user__username', 'user__name', 'created_by__username')
    readonly_fields = ('user', 'source', 'source_id', 'before', 'after', 'created_at', 'created_by')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {'GET', 'HEAD', 'OPTIONS'}

    def has_delete_permission(self, request, obj=None):
        return False
