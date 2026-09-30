from django.urls import path
from .views_dashboard import dashboard_stats
from .dashboard_operations import operations
from .quarter_views import quarter_current, quarter_snapshots, quarter_snapshot_detail
from .selic_views import selic_table, selic_rate_detail

urlpatterns = [
    path("selic/", selic_table, name="selic-table"),
    path("selic/<int:year>/<int:month>/", selic_rate_detail, name="selic-rate-detail"),
    path("quarters/current/", quarter_current, name="quarter-current"),
    path("quarters/snapshots/", quarter_snapshots, name="quarter-snapshots"),
    path("quarters/snapshots/<uuid:public_id>/", quarter_snapshot_detail, name="quarter-snapshot-detail"),
    path("operations/", operations, name="dashboard-operations"),
    path("dashboard/stats/", dashboard_stats, name="dashboard-stats"),
]
