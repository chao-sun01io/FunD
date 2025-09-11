from django.contrib import admin
from django.conf import settings
# Register your models here.
from .models import FundBasicInfo, FundDailyData

admin.site.register(FundBasicInfo)

if settings.DEBUG:
    admin.site.register(FundDailyData)

