from django.urls import path
from . import views
from .daily_report import daily_report

urlpatterns = [
    path("daily-report/", daily_report, name="audit-daily-report"),
    path("logs/", views.list_audit_logs, name="audit-logs-list"),
    path("recent-logs/", views.recent_audit_logs, name="audit-logs-recent"),
    path("my-logs/", views.my_audit_logs, name="audit-logs-my"),
]
