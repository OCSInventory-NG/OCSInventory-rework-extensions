from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import ProxmoxAssetViewSet, ProxmoxServerViewSet

router = DefaultRouter()
router.register(r"servers", ProxmoxServerViewSet, basename="proxmoxserver")
router.register(r"assets", ProxmoxAssetViewSet, basename="proxmoxasset")

urlpatterns = [
    path("", include(router.urls)),
]
