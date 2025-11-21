# AI Coding Agent Instructions for Miele System

## Overview

The **Miele System** is an enterprise management software focused on **Clients** and **PER/DCOMPs** (tax documents). It is built with **Django 5.x**, **Django REST Framework (DRF)**, and follows an **API-first** architecture. Key features include JWT authentication, RBAC, audit logging, and modular app design.

## Architecture

- **Core Components:**
  - `identity`: Handles authentication (JWT, 2FA, rate limiting) and RBAC.
  - `clients`: Manages client lifecycle, approval workflows, and auditing.
  - `perdcomps`: Manages tax documents linked to clients.
  - `common`: Shared utilities, permissions, and services.
  - `core`: Project settings, middleware, and URL routing.
- **Data Flow:**
  - Requests are routed through `core/urls.py` to app-specific routers.
  - Authentication and permissions are enforced globally via middleware and app-specific policies.
  - Audit logs and approval workflows are triggered automatically for sensitive operations.
- **External Integrations:**
  - **BrasilAPI**: Used for CNPJ validation.
  - **S3**: Planned for file storage.
  - **Redis + Celery**: For asynchronous tasks like email notifications.

## Developer Workflows

### Build and Run

- **Local Development:**
  ```bash
  docker-compose up --build
  ```
- **Apply Migrations:**
  ```bash
  python manage.py migrate
  ```
- **Run Tests:**
  ```bash
  pytest
  ```
- **Create Superuser:**
  ```bash
  python manage.py create_superuser_with_role
  ```

### Debugging

- **Health Checks:**
  - `/health/live`: Liveness probe.
  - `/health/ready`: Readiness probe.
- **Logs:**
  - Structured JSON logs are configured for observability.

## Project-Specific Conventions

- **Modular Design:**
  - Each app (`identity`, `clients`, `perdcomps`) has its own `models.py`, `serializers.py`, `views.py`, and `urls.py`.
- **Approval Workflows:**
  - Sensitive operations (e.g., client updates) require approval requests.
  - Implemented in `common/approvals/`.
- **Audit Logging:**
  - Automatically logs changes to sensitive models.
  - Implemented in `common/audit/`.
- **RBAC:**
  - Roles and permissions are defined in `common/permissions.py`.

## Key Files and Directories

- `backend/core/settings/`: Environment-specific settings (`base.py`, `dev.py`, `prod.py`).
- `backend/common/`: Shared utilities, permissions, and services.
- `backend/api/routers.py`: Centralized API routing.
- `docs/`: Architectural decisions, use cases, and database schema.

## Integration Points

- **BrasilAPI:**
  - Used for validating CNPJ numbers in the `clients` app.
- **Celery Tasks:**
  - Planned for asynchronous operations like email notifications.
- **S3 Storage:**
  - Planned for file uploads.

## Examples

### Serializer Example

```python
class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name', 'email', 'is_active']
```

### Viewset Example

```python
class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
```

### Celery Task Example

```python
@app.task
def send_email_notification(email, subject, message):
    send_mail(subject, message, 'noreply@miele.com', [email])
```

## Admin Backoffice Setup

The `admin_backoffice` app is configured using **django-jazzmin** to provide a modern and user-friendly administrative interface. Below are the key details:

### Installation and Configuration

- **Installed Package:** `django-jazzmin` is added to `INSTALLED_APPS` in `settings/base.py`.
- **Customizations:** The admin interface is themed with Jazzmin settings to align with the project's UX goals, including:
  - Dark mode support.
  - Custom menu structure for navigating `Identity`, `Clients`, `PER/DCOMPs`, and `Logs`.
  - Enhanced filters and search capabilities.

### Features

- **Dashboard:** Displays key metrics such as active users, pending requests, and recent activities.
- **2FA Integration:** Enforces TOTP-based two-factor authentication for all staff users.
- **RBAC:** Role-based access control is implemented using Django groups and permissions.
- **Custom Views:** Auxiliary pages for approvals, logs, and client supervision are added under `admin_backoffice/`.

### Key Files

- `apps/admin_backoffice/admin.py`: Registers models and customizes the admin interface.
- `apps/admin_backoffice/views.py`: Contains views for dashboards and auxiliary pages.
- `templates/admin/`: Overrides default Django admin templates.
- `static/backoffice/`: Contains additional CSS/JS for the admin interface.

### Testing

- Verify the admin interface for functionality, security (2FA, CSRF), and UX (navigation, filters).
- Ensure all role-based permissions are enforced correctly.

---

For more details, refer to the [README.md](../README.md) and documentation in the `docs/` folder.
