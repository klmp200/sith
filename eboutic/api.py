# -*- coding:utf-8 -*
#
# Copyright 2022
# - Maréchal <thgirod@outlook.com>
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


import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_POST

from counter.models import Counter, Product
from eboutic.models import Basket


@require_POST
@login_required
def add_product(request: HttpRequest, product_id: int) -> HttpResponse:
    """
    POST request that adds in the basket an item corresponding to the product which primary
    key is passed as an url parameter, then returns a JSON response describing the new state of the basket
    If the response has 404 status, then the json response is empty.

    Example of json response: ::

            {
                "total": 45.67  <- total price of the basket
                "items": [
                    {
                        "product_id": 3,
                        "quantity": 2
                    },
                    {
                        "product_id": 5,
                        "quantity": 3
                    }
                ]
            }

    """
    basket = Basket.from_request(request)
    try:
        product = Counter.objects.get(type="EBOUTIC").products.get(id=product_id)
    except Product.DoesNotExist:
        content = json.dumps({"error_msg": "This product does not exist"})
        return HttpResponse(
            status=404, content_type="application/json", content=content
        )
    if product.can_be_sold_to(request.user):
        basket.add_product(product)
    else:
        content = json.dumps(
            {"error_msg": "You do not have have rights to add this product"}
        )
        return HttpResponse(
            status=403, content_type="application/json", content=content
        )
    basket.save()
    res = {
        "total": basket.get_total(),
        "items": list(basket.items.all().values("product_id", "quantity")),
    }
    return HttpResponse(
        status=200, content_type="application/json", content=json.dumps(res)
    )


@require_POST
@login_required
def remove_product(request: HttpRequest, product_id: int) -> HttpResponse:
    """
    POST request that removes from the basket an item corresponding to the product which primary
    key is passed as an url parameter, then returns a JSON response describing the new state of the basket
    If the response has 404 status, then the json response is empty.

    Example of json response: ::

        {
            "total": 24.30
            "items": [
                {
                    "product_id": 3,
                    "quantity": 2
                },
                {
                    "product_id": 5,
                    "quantity": 1
                }
            ]
        }
    """
    basket = Basket.from_request(request)
    try:
        product = Counter.objects.get(type="EBOUTIC").products.get(id=product_id)
    except Product.DoesNotExist:
        content = json.dumps({"error_msg": "This product does not exist"})
        return HttpResponse(
            status=404, content_type="application/json", content=content
        )
    basket.del_product(product)
    res = {
        "total": basket.get_total(),
        "items": list(basket.items.all().values("product_id", "quantity")),
    }
    return HttpResponse(
        status=200, content_type="application/json", content=json.dumps(res)
    )


@require_POST
@login_required
def clear_basket(request: HttpRequest) -> HttpResponse:
    """
    Remove all items from the basket referenced in the session of the
    user who makes this request.
    """
    if "basket_id" in request.session:
        try:
            basket = Basket.objects.get(id=request.session["basket_id"])
            basket.clear()
            return HttpResponse("Cleared", status=200)
        except Basket.DoesNotExist:
            return HttpResponse("No basket is currently used", status=404)
    else:
        return HttpResponse("No basket is currently used", status=404)

