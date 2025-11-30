from django.urls import path
from . import views

urlpatterns = [
    path("logs/", views.list_audit_logs, name="audit-logs-list"),
    path("recent-logs/", views.recent_audit_logs, name="audit-logs-recent"),
    path("my-logs/", views.my_audit_logs, name="audit-logs-my"),
]
