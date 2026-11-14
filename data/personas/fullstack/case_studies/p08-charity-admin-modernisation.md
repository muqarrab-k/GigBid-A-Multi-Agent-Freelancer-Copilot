# Charity admin modernisation

In late 2022, I worked with **Oakfield Charities** on an hourly engagement to modernise a critical donor administration system. Their existing platform was built on an older Django codebase, and the team needed a safer, faster way to handle donation entry without disrupting day-to-day operations or compromising long-standing donor data.

My main focus was upgrading the application from **Django 1.11 to Django 4.1** while keeping the system stable throughout the transition. Because the donor records were already substantial, I approached the work incrementally: first validating the database and application paths, then updating the codebase to run cleanly on the newer framework, and finally rebuilding the most important user-facing workflow — the donation entry screens.

To improve the day-to-day experience for staff, I rebuilt those screens with **HTMX**, so the interface could feel much more responsive without introducing unnecessary complexity on the frontend. This allowed me to keep the interaction model simple while still reducing friction for the people entering donations. On the backend, I used **PostgreSQL** for the data layer and **Celery** for asynchronous work where background processing was needed.

A big part of the project was making sure the upgrade was not just functional, but trustworthy. I paid close attention to database compatibility, record handling, and rollout sequencing so the system could move forward without data issues. The result was a clean platform upgrade with no disruption to the donor base.

```python
# Django 4.1 + HTMX view for donation entry
from django.shortcuts import render
from django.views import View

class DonationEntryView(View):
    def get(self, request):
        return render(request, "donations/entry_form.html")

    def post(self, request):
        # validate and save donation data
        return render(request, "donations/entry_success.html")
```

The outcome was strong: **donation entry time dropped by 45%**, and we preserved **zero data loss across 180k donor records**. For Oakfield Charities, that meant a more efficient internal workflow and a modernised system they could continue to rely on.
