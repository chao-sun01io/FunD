It uses celery as a task queue to handle background tasks in a Django application. 

# Tasks
This document outlines the tasks that can be performed using Celery in the Django application.

- get pcf in a daily basis
- get the fund basic data when the market is closed, and update the database `info_fundbasicinfo`
    - for US listed funds, we might also get the nightly data from the US market
- get composition security live data in a secondly basis

# Scheduler
We use `django-celery-beat` to manage periodic tasks. 
