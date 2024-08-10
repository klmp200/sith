#
# Copyright 2016,2017
# - Skia <skia@libskia.so>
# - Sli <antoine@bartuccio.fr>
#
# Ce fichier fait partie du site de l'Association des Étudiants de l'UTBM,
# http://ae.utbm.fr.
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License a published by the Free Software
# Foundation; either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 59 Temple
# Place - Suite 330, Boston, MA 02111-1307, USA.
#
#

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import serializers
from django.db.models.query import QuerySet
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import html
from django.utils.text import slugify
from django.views.generic import ListView
from haystack.query import SearchQuerySet

from club.models import Club
from core.models import Notification, User


def index(request, context=None):
    from com.views import NewsListView

    return NewsListView.as_view()(request)


class NotificationList(ListView):
    model = Notification
    template_name = "core/notification_list.jinja"

    def get_queryset(self) -> QuerySet[Notification]:
        if self.request.user.is_anonymous:
            return Notification.objects.none()
        # TODO: Bulk update in django 2.2
        if "see_all" in self.request.GET.keys():
            for n in self.request.user.notifications.filter(viewed=False):
                n.viewed = True
                n.save()

        return self.request.user.notifications.order_by("-date")[:20]


def notification(request, notif_id):
    notif = Notification.objects.filter(id=notif_id).first()
    if notif:
        if notif.type not in settings.SITH_PERMANENT_NOTIFICATIONS:
            notif.viewed = True
        else:
            notif.callback()
        notif.save()
        return redirect(notif.url)
    return redirect("/")


def search_user(query):
    try:
        # slugify turns everything into ascii and every whitespace into -
        # it ends by removing duplicate - (so ' - ' will turn into '-')
        # replace('-', ' ') because search is whitespace based
        query = slugify(query).replace("-", " ")
        # TODO: is this necessary?
        query = html.escape(query)
        res = (
            SearchQuerySet()
            .models(User)
            .autocomplete(auto=query)
            .order_by("-last_update")[:20]
        )
        return [r.object for r in res]
    except TypeError:
        return []


def search_club(query, *, as_json=False):
    clubs = []
    if query:
        clubs = Club.objects.filter(name__icontains=query).all()
        clubs = clubs[:5]
        if as_json:
            # Re-loads json to avoid double encoding by JsonResponse, but still benefit from serializers
            clubs = json.loads(serializers.serialize("json", clubs, fields=("name")))
        else:
            clubs = list(clubs)
    return clubs


@login_required
def search_view(request):
    result = {
        "users": search_user(request.GET.get("query", "")),
        "clubs": search_club(request.GET.get("query", "")),
    }
    return render(request, "core/search.jinja", context={"result": result})


@login_required
def search_user_json(request):
    result = {"users": search_user(request.GET.get("query", ""))}
    return JsonResponse(result)


@login_required
def search_json(request):
    result = {
        "users": search_user(request.GET.get("query", "")),
        "clubs": search_club(request.GET.get("query", ""), as_json=True),
    }
    return JsonResponse(result)
