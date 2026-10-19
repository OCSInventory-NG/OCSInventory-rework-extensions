from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ADComputerViewSet, ADDomainViewSet, SyncReportViewSet

router = DefaultRouter()
router.register(r"domains", ADDomainViewSet, basename="addomain")
router.register(r"computers", ADComputerViewSet, basename="adcomputer")
router.register(r"reports", SyncReportViewSet, basename="adsyncreport")

urlpatterns = [
    path("", include(router.urls)),
]
