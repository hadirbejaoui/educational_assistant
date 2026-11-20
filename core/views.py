from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services.dashboard import dashboard_data


@login_required
def dashboard(request):
    return render(request, "dashboard.html", dashboard_data(request.user))
