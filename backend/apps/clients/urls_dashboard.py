from django.urls import path
from .views_dashboard import dashboard_stats
from .dashboard_operations import operations
from .quarter_views import quarter_current, quarter_snapshots, quarter_snapshot_detail

urlpatterns = [
    path("quarters/current/", quarter_current, name="quarter-current"),
    path("quarters/snapshots/", quarter_snapshots, name="quarter-snapshots"),
    path("quarters/snapshots/<uuid:public_id>/", quarter_snapshot_detail, name="quarter-snapshot-detail"),
    path("operations/", operations, name="dashboard-operations"),
    path("dashboard/stats/", dashboard_stats, name="dashboard-stats"),
]
