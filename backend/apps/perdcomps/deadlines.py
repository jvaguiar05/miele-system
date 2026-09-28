"""Shared operational calendar for due dates, dashboard and reports."""
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.conf import settings

OPEN_STATUSES = {"TRANSMITIDO", "EM_PROCESSAMENTO", "PARCIALMENTE_DEFERIDO", "VENCIDO"}


def business_day(day):
    fixed = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}
    extra = getattr(settings, "DASHBOARD_EXTRA_HOLIDAYS", [])
    return day.weekday() < 5 and (day.month, day.day) not in fixed and day.isoformat() not in extra


def alert_start(due):
    remaining = 30
    while remaining:
        due -= timedelta(days=1)
        if business_day(due):
            remaining -= 1
    return due


def automatic_due_date(transmission):
    due = transmission + relativedelta(years=1)
    while not business_day(due):
        due += timedelta(days=1)
    return due
