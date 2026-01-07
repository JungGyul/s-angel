# applications/templatetags/app_filters.py
from django import template

register = template.Library()

@register.filter
def get_draw_status(event_status_list, event_id):
    for item in event_status_list:
        if item['event'].id == event_id:
            return item['is_drawn']
    return False

# applications/templatetags/app_filters.py

@register.filter
def get_finalized_status(event_status_list, event_id):
    for item in event_status_list:
        if item['event'].id == event_id:
            return item['is_finalized']
    return False