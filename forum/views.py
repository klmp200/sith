# -*- coding:utf-8 -*
#
# Copyright 2016,2017,2018
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
# this program; if not, write to the Free Sofware Foundation, Inc., 59 Temple
# Place - Suite 330, Boston, MA 02111-1307, USA.
#
#

from django.shortcuts import get_object_or_404
from django.views.generic import ListView, DetailView, RedirectView
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django.views.generic.detail import SingleObjectMixin
from django.utils.translation import ugettext_lazy as _
from django.core.urlresolvers import reverse_lazy
from django.utils import timezone
from django.conf import settings
from django import forms
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from ajax_select import make_ajax_field

from core.views import CanViewMixin, CanEditMixin, CanEditPropMixin, CanCreateMixin
from core.views.forms import MarkdownInput
from forum.models import Forum, ForumMessage, ForumTopic, ForumMessageMeta
from haystack.query import SearchQuerySet


class ForumSearchView(CanViewMixin, ListView):
    template_name = "forum/search.jinja"

    def get_queryset(self):
        query = self.request.GET.get("query", "")
        return SearchQuerySet().models(ForumMessage).autocomplete(auto=query)
        # return [r.object for r in q]


class ForumMainView(ListView):
    queryset = Forum.objects.filter(parent=None).prefetch_related(
        "children___last_message__author", "children___last_message__topic"
    )
    template_name = "forum/main.jinja"


class ForumMarkAllAsRead(RedirectView):
    permanent = False
    url = reverse_lazy("forum:last_unread")

    def get(self, request, *args, **kwargs):
        try:
            fi = request.user.forum_infos
            fi.last_read_date = timezone.now()
            fi.save()
            for m in request.user.read_messages.filter(date__lt=fi.last_read_date):
                m.readers.remove(request.user)  # Clean up to keep table low in data
        except:
            pass
        return super(ForumMarkAllAsRead, self).get(request, *args, **kwargs)


class ForumFavoriteTopics(ListView):
    model = ForumTopic
    template_name = "forum/favorite_topics.jinja"
    paginate_by = settings.SITH_FORUM_PAGE_LENGTH / 2

    def get_queryset(self):
        topic_list = self.request.user.favorite_topics.all()
        return topic_list


class ForumLastUnread(ListView):
    model = ForumTopic
    template_name = "forum/last_unread.jinja"
    paginate_by = settings.SITH_FORUM_PAGE_LENGTH / 2

    def get_queryset(self):
        topic_list = (
            self.model.objects.filter(
                _last_message__date__gt=self.request.user.forum_infos.last_read_date
            )
            .exclude(_last_message__readers=self.request.user)
            .order_by("-_last_message__date")
            .select_related("_last_message__author", "author")
            .prefetch_related("forum__edit_groups")
        )
        return topic_list


class ForumNameField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name()


class ForumForm(forms.ModelForm):
    class Meta:
        model = Forum
        fields = [
            "name",
            "parent",
            "number",
            "owner_club",
            "is_category",
            "edit_groups",
            "view_groups",
        ]

    edit_groups = make_ajax_field(Forum, "edit_groups", "groups", help_text="")
    view_groups = make_ajax_field(Forum, "view_groups", "groups", help_text="")
    parent = ForumNameField(Forum.objects.all())


class ForumCreateView(CanCreateMixin, CreateView):
    model = Forum
    form_class = ForumForm
    template_name = "core/create.jinja"

    def get_initial(self):
        init = super(ForumCreateView, self).get_initial()
        try:
            parent = Forum.objects.filter(id=self.request.GET["parent"]).first()
            init["parent"] = parent
            init["owner_club"] = parent.owner_club
            init["edit_groups"] = parent.edit_groups.all()
            init["view_groups"] = parent.view_groups.all()
        except:
            pass
        return init


class ForumEditForm(ForumForm):
    recursive = forms.BooleanField(
        label=_("Apply rights and club owner recursively"), required=False
    )


class ForumEditView(CanEditPropMixin, UpdateView):
    model = Forum
    pk_url_kwarg = "forum_id"
    form_class = ForumEditForm
    template_name = "core/edit.jinja"
    success_url = reverse_lazy("forum:main")

    def form_valid(self, form):
        ret = super(ForumEditView, self).form_valid(form)
        if form.cleaned_data["recursive"]:
            self.object.apply_rights_recursively()
        return ret


class ForumDeleteView(CanEditPropMixin, DeleteView):
    model = Forum
    pk_url_kwarg = "forum_id"
    template_name = "core/delete_confirm.jinja"
    success_url = reverse_lazy("forum:main")


class ForumDetailView(CanViewMixin, DetailView):
    model = Forum
    template_name = "forum/forum.jinja"
    pk_url_kwarg = "forum_id"

    def get_context_data(self, **kwargs):
        kwargs = super(ForumDetailView, self).get_context_data(**kwargs)
        qs = (
            self.object.topics.order_by("-_last_message__date")
            .select_related("_last_message__author", "author")
            .prefetch_related("forum__edit_groups")
        )
        paginator = Paginator(qs, settings.SITH_FORUM_PAGE_LENGTH)
        page = self.request.GET.get("topic_page")
        try:
            kwargs["topics"] = paginator.page(page)
        except PageNotAnInteger:
            kwargs["topics"] = paginator.page(1)
        except EmptyPage:
            kwargs["topics"] = paginator.page(paginator.num_pages)
        return kwargs


class TopicForm(forms.ModelForm):
    class Meta:
        model = ForumMessage
        fields = ["title", "message"]
        widgets = {"message": MarkdownInput}

    title = forms.CharField(required=True, label=_("Title"))


class ForumTopicCreateView(CanCreateMixin, CreateView):
    model = ForumMessage
    form_class = TopicForm
    template_name = "forum/reply.jinja"

    def dispatch(self, request, *args, **kwargs):
        self.forum = get_object_or_404(
            Forum, id=self.kwargs["forum_id"], is_category=False
        )
        if not request.user.can_view(self.forum):
            raise PermissionDenied
        return super(ForumTopicCreateView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        topic = ForumTopic(
            _title=form.instance.title, author=self.request.user, forum=self.forum
        )
        topic.save()
        form.instance.topic = topic
        form.instance.author = self.request.user
        return super(ForumTopicCreateView, self).form_valid(form)


class ForumTopicEditView(CanEditMixin, UpdateView):
    model = ForumTopic
    fields = ["forum"]
    pk_url_kwarg = "topic_id"
    template_name = "core/edit.jinja"


class ForumTopicSubscribeView(CanViewMixin, SingleObjectMixin, RedirectView):
    model = ForumTopic
    pk_url_kwarg = "topic_id"
    permanent = False

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if request.user in self.object.subscribed_users.all():
            self.object.subscribed_users.remove(request.user)
        else:
            self.object.subscribed_users.add(request.user)
        return super().get(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        return self.object.get_absolute_url()


class ForumTopicDetailView(CanViewMixin, DetailView):
    model = ForumTopic
    pk_url_kwarg = "topic_id"
    template_name = "forum/topic.jinja"
    context_object_name = "topic"
    queryset = ForumTopic.objects.select_related("forum__parent")

    def get_context_data(self, **kwargs):
        kwargs = super(ForumTopicDetailView, self).get_context_data(**kwargs)
        try:
            msg = self.object.get_first_unread_message(self.request.user)
            kwargs["first_unread_message_id"] = msg.id
        except:
            kwargs["first_unread_message_id"] = float("inf")
        paginator = Paginator(
            self.object.messages.select_related("author__avatar_pict")
            .prefetch_related("topic__forum__edit_groups", "readers")
            .order_by("date"),
            settings.SITH_FORUM_PAGE_LENGTH,
        )
        page = self.request.GET.get("page")
        try:
            kwargs["msgs"] = paginator.page(page)
        except PageNotAnInteger:
            kwargs["msgs"] = paginator.page(1)
        except EmptyPage:
            kwargs["msgs"] = paginator.page(paginator.num_pages)
        return kwargs


class ForumMessageView(SingleObjectMixin, RedirectView):
    model = ForumMessage
    pk_url_kwarg = "message_id"
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        self.object = self.get_object()
        return self.object.get_url()


class ForumMessageEditView(CanEditMixin, UpdateView):
    model = ForumMessage
    form_class = forms.modelform_factory(
        model=ForumMessage,
        fields=["title", "message"],
        widgets={"message": MarkdownInput},
    )
    template_name = "forum/reply.jinja"
    pk_url_kwarg = "message_id"

    def form_valid(self, form):
        ForumMessageMeta(
            message=self.object, user=self.request.user, action="EDIT"
        ).save()
        return super(ForumMessageEditView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        kwargs = super(ForumMessageEditView, self).get_context_data(**kwargs)
        kwargs["topic"] = self.object.topic
        return kwargs


class ForumMessageDeleteView(SingleObjectMixin, RedirectView):
    model = ForumMessage
    pk_url_kwarg = "message_id"
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        self.object = self.get_object()
        if self.object.can_be_moderated_by(self.request.user):
            ForumMessageMeta(
                message=self.object, user=self.request.user, action="DELETE"
            ).save()
        return self.object.get_absolute_url()


class ForumMessageUndeleteView(SingleObjectMixin, RedirectView):
    model = ForumMessage
    pk_url_kwarg = "message_id"
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        self.object = self.get_object()
        if self.object.can_be_moderated_by(self.request.user):
            ForumMessageMeta(
                message=self.object, user=self.request.user, action="UNDELETE"
            ).save()
        return self.object.get_absolute_url()


class ForumMessageCreateView(CanCreateMixin, CreateView):
    model = ForumMessage
    form_class = forms.modelform_factory(
        model=ForumMessage,
        fields=["title", "message"],
        widgets={"message": MarkdownInput},
    )
    template_name = "forum/reply.jinja"

    def dispatch(self, request, *args, **kwargs):
        self.topic = get_object_or_404(ForumTopic, id=self.kwargs["topic_id"])
        if not request.user.can_view(self.topic):
            raise PermissionDenied
        return super(ForumMessageCreateView, self).dispatch(request, *args, **kwargs)

    def get_initial(self):
        init = super(ForumMessageCreateView, self).get_initial()
        try:
            message = (
                ForumMessage.objects.select_related("author")
                .filter(id=self.request.GET["quote_id"])
                .first()
            )
            init["message"] = "> ##### %s\n" % (
                _("%(author)s said") % {"author": message.author.get_short_name()}
            )
            init["message"] += "\n".join(
                ["> " + line for line in message.message.split("\n")]
            )
            init["message"] += "\n\n"
        except Exception as e:
            print(repr(e))
        return init

    def form_valid(self, form):
        form.instance.topic = self.topic
        form.instance.author = self.request.user
        return super(ForumMessageCreateView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        kwargs = super(ForumMessageCreateView, self).get_context_data(**kwargs)
        kwargs["topic"] = self.topic
        return kwargs
