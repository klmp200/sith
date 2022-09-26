from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_POST

from counter.models import Counter, Product
from eboutic.models import Basket


def __get_basket(request: HttpRequest) -> Basket:
    if "basket_id" in request.session:
        try:
            return Basket.objects.get(id=request.session["basket_id"])
        except Basket.DoesNotExist:
            return Basket(user=request.user)
    else:
        return Basket(user=request.user)


@require_POST
@login_required
def add_product(request: HttpRequest, product_id: int) -> HttpResponse:
    basket = __get_basket(request)
    try:
        product = Counter.objects.get(type="EBOUTIC").products.get(id=product_id)
    except Product.DoesNotExist:
        return HttpResponse("Product does not exist", status=404)
    if product.can_be_sold_to(request.user):
        basket.add_product(product)
    basket.save()
    request.session["basket_id"] = basket.id
    request.session.modified = True
    return HttpResponse("Ok", status=200)


@require_POST
@login_required
def remove_product(request: HttpRequest, product_id: int) -> HttpResponse:
    basket = __get_basket(request)
    try:
        product = Counter.objects.get(type="EBOUTIC").products.get(id=product_id)
    except Product.DoesNotExist:
        return HttpResponse("Product does not exist", status=404)
    basket.del_product(product)
    return HttpResponse("Ok", status=200)
