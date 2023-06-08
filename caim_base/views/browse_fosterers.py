from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.gis.db.models.functions import Distance

from caim_base.models.fosterer import FostererProfile, query_fostererprofiles

from ..animal_search import query_animals

from ..models.geo import ZipCode


def parse_radius(args):
    if not args.get("zip"):
        return None
    if "radius" not in args:
        return None  # Temp change to default to any not 50
    if args["radius"] == "any":
        return None
    return int(args["radius"])




def view(request):

    current_page = int(request.GET.get("page", 1))
    npp = int(request.GET.get("limit", 12))

    query = query_fostererprofiles()
    paginator = Paginator(query.all(), npp)
    fosterers = paginator.page(current_page)

    context = {
        "behavioural_attributes": dict(FostererProfile.BehaviouralAttributes.choices),
        "paginator": paginator,
        "fosterers": fosterers,
    }
    return render(request, "browse_fosterers.html", context)
