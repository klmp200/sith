# -*- coding:utf-8 -*
#
# Copyright 2016,2017
# - Skia <skia@libskia.so>
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

import base64
import hmac
import json
from collections import OrderedDict
from datetime import datetime

from OpenSSL import crypto
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousOperation, PermissionDenied
from django.db import transaction, DataError, DatabaseError
from django.db.models import F
from django.http import HttpResponse, HttpRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import TemplateView, View

import core.views
import sith.urls
from counter.models import Customer, Counter, Selling, Product
from eboutic.exceptions import (
    CookieEmpty,
    CookieNegativeIndex,
    CookieImproperlyFormatted,
    EbouticCookieError,
)
from eboutic.models import Basket, Invoice, InvoiceItem


@login_required
@require_GET
def eboutic_main(request: HttpRequest) -> HttpResponse:
    products = (
        Counter.objects.get(type="EBOUTIC")
        .products.exclude(product_type__isnull=True)
        .annotate(category=F("product_type__name"))
    )
    if not request.user.subscriptions.exists():
        products = products.exclude(settings.SITH_PRODUCTTYPE_SUBSCRIPTION)
    context = {
        "products": products,
        "customer_amount": request.user.account_balance,
    }
    return render(request, "eboutic/eboutic_main.jinja", context)


@require_GET
@login_required
def payment_result(request, result: str) -> HttpResponse:
    context = {"success": result == "success"}
    return render(request, "eboutic/eboutic_payment_result.jinja", context)


class EbouticCommand(TemplateView):
    template_name = "eboutic/eboutic_makecommand.jinja"

    @method_decorator(login_required)
    def get(self, request, *args, **kwargs):
        return redirect("eboutic:main")

    @staticmethod
    def __check_cookies(cookies: list) -> None:
        if len(cookies) == 0:
            raise CookieEmpty()
        for cookie in cookies:
            if any(key not in cookie for key in ("id", "quantity")):
                raise CookieImproperlyFormatted()
            if cookie["quantity"] < 0:
                raise CookieNegativeIndex()

    @method_decorator(login_required)
    def post(self, request: HttpRequest, *args, **kwargs):
        req_basket = json.loads(request.COOKIES.get("basket_items", "[]"))
        try:
            self.__check_cookies(req_basket)
        except EbouticCookieError as e:
            res = e.get_redirection(request)
            res.delete_cookie("basket_items", "/eboutic")
            return res
        if "basket_id" in request.session:
            basket, _ = Basket.objects.get_or_create(
                id=request.session["basket_id"], user=request.user
            )
            basket.clear()
        else:
            basket = Basket.objects.create(user=request.user)
        basket.save()
        for item in req_basket:
            eboutique = Counter.objects.get(type="EBOUTIC")
            try:
                product = eboutique.products.get(id=(item["id"]))
            except Product.DoesNotExist:
                res = redirect("eboutic:main")
                res.delete_cookie("basket_items", "/eboutic")
                return res
            if not product.can_be_sold_to(request.user):
                res = redirect("eboutic:main")
                res.delete_cookie("basket_items", "/eboutic")
                return res
            basket.add_product(product, item["quantity"])
        request.session["basket_id"] = basket.id
        request.session.modified = True
        kwargs["basket"] = basket
        return self.render_to_response(self.get_context_data(**kwargs))

    def get_context_data(self, **kwargs):
        kwargs = super(EbouticCommand, self).get_context_data(**kwargs)
        if hasattr(self.request.user, "customer"):
            kwargs["customer_amount"] = self.request.user.customer.amount
        else:
            kwargs["customer_amount"] = None
        kwargs["et_request"] = OrderedDict()
        kwargs["et_request"]["PBX_SITE"] = settings.SITH_EBOUTIC_PBX_SITE
        kwargs["et_request"]["PBX_RANG"] = settings.SITH_EBOUTIC_PBX_RANG
        kwargs["et_request"]["PBX_IDENTIFIANT"] = settings.SITH_EBOUTIC_PBX_IDENTIFIANT
        kwargs["et_request"]["PBX_TOTAL"] = int(kwargs["basket"].get_total() * 100)
        kwargs["et_request"][
            "PBX_DEVISE"
        ] = 978  # This is Euro. ET support only this value anyway
        kwargs["et_request"]["PBX_CMD"] = kwargs["basket"].id
        kwargs["et_request"]["PBX_PORTEUR"] = kwargs["basket"].user.email
        kwargs["et_request"]["PBX_RETOUR"] = "Amount:M;BasketID:R;Auto:A;Error:E;Sig:K"
        kwargs["et_request"]["PBX_HASH"] = "SHA512"
        kwargs["et_request"]["PBX_TYPEPAIEMENT"] = "CARTE"
        kwargs["et_request"]["PBX_TYPECARTE"] = "CB"
        kwargs["et_request"]["PBX_TIME"] = str(
            datetime.now().replace(microsecond=0).isoformat("T")
        )
        kwargs["et_request"]["PBX_HMAC"] = (
            hmac.new(
                settings.SITH_EBOUTIC_HMAC_KEY,
                bytes(
                    "&".join(
                        ["%s=%s" % (k, v) for k, v in kwargs["et_request"].items()]
                    ),
                    "utf-8",
                ),
                "sha512",
            )
            .hexdigest()
            .upper()
        )
        return kwargs


@login_required
@require_POST
def pay_with_sith(request):
    basket = Basket.from_session(request.session)
    refilling = settings.SITH_COUNTER_PRODUCTTYPE_REFILLING
    if basket is None or basket.items.filter(type_id=refilling).exists():
        return redirect("eboutic:main")
    c = Customer.objects.filter(user__id=basket.user.id).first()
    if c is None:
        return redirect("eboutic:main")
    if c.amount < basket.get_total():
        res = redirect("eboutic:payment_result", "failure")
    else:
        eboutic = Counter.objects.filter(type="EBOUTIC").first()
        try:
            with transaction.atomic():
                for it in basket.items.all():
                    product = eboutic.products.get(id=it.product_id)
                    Selling(
                        label=it.product_name,
                        counter=eboutic,
                        club=product.club,
                        product=product,
                        seller=c.user,
                        customer=c,
                        unit_price=it.product_unit_price,
                        quantity=it.quantity,
                        payment_method="SITH_ACCOUNT",
                    ).save()
                basket.delete()
                request.session.pop("basket_id", None)
                res = redirect("eboutic:payment_result", "success")
        except DatabaseError:
            res = redirect("eboutic:payment_result", "failure")
    res.delete_cookie("basket_items", "/eboutic")
    return res


class EtransactionAutoAnswer(View):
    # Response documentation http://www1.paybox.com/espace-integrateur-documentation
    # /la-solution-paybox-system/gestion-de-la-reponse/
    def get(self, request, *args, **kwargs):
        if (
            not "Amount" in request.GET.keys()
            or not "BasketID" in request.GET.keys()
            or not "Error" in request.GET.keys()
            or not "Sig" in request.GET.keys()
        ):
            return HttpResponse("Bad arguments", status=400)
        key = crypto.load_publickey(crypto.FILETYPE_PEM, settings.SITH_EBOUTIC_PUB_KEY)
        cert = crypto.X509()
        cert.set_pubkey(key)
        sig = base64.b64decode(request.GET["Sig"])
        try:
            crypto.verify(
                cert,
                sig,
                "&".join(request.META["QUERY_STRING"].split("&")[:-1]).encode("utf-8"),
                "sha1",
            )
        except:
            return HttpResponse("Bad signature", status=400)
        # Payment authorized:
        # * 'Error' is '00000'
        # * 'Auto' is in the request
        if request.GET["Error"] == "00000" and "Auto" in request.GET.keys():
            try:
                with transaction.atomic():
                    b = (
                        Basket.objects.select_for_update()
                        .filter(id=request.GET["BasketID"])
                        .first()
                    )
                    if b is None:
                        raise SuspiciousOperation("Basket does not exists")
                    if int(b.get_total() * 100) != int(request.GET["Amount"]):
                        raise SuspiciousOperation(
                            "Basket total and amount do not match"
                        )
                    i = Invoice()
                    i.user = b.user
                    i.payment_method = "CARD"
                    i.save()
                    for it in b.items.all():
                        InvoiceItem(
                            invoice=i,
                            product_id=it.product_id,
                            product_name=it.product_name,
                            type_id=it.type_id,
                            product_unit_price=it.product_unit_price,
                            quantity=it.quantity,
                        ).save()
                    i.validate()
                    b.delete()
            except Exception as e:
                return HttpResponse(
                    "Basket processing failed with error: " + repr(e), status=500
                )
            return HttpResponse("Payment successful", status=200)
        else:
            return HttpResponse(
                "Payment failed with error: " + request.GET["Error"], status=202
            )
