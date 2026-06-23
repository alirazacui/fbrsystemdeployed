"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
 
urlpatterns = [
    path("admin/",  admin.site.urls),
 
    # All API endpoints under /api/
    path("api/", include("companies.urls")),
    path("api/", include("users.urls")),
    path("api/", include("permission_app.urls")),
    path("api/",include("pos.urls")),
    path("api/", include("digital_invoicing.urls")),
]
 
# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
 
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


from celery.schedules import crontab
 
CELERY_BEAT_SCHEDULE = {
    # Retry failed FBR submissions every 15 minutes
    "retry-failed-fbr-submissions": {
        "task":     "digital_invoicing.retry_failed_submissions",
        "schedule": crontab(minute="*/15"),
    },
}