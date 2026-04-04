from django.urls import path
from . import views, api

urlpatterns = [
    path("", views.index, name="index"),
    path("<str:symbol>/history", api.fund_history, name="fund_history"),
    path("<str:symbol>", views.detail, name="detail"),
]