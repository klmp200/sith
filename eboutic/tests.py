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
import json
import re
import urllib

from OpenSSL import crypto
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import User
from counter.models import Product, Counter, Customer, Selling
from eboutic.models import Basket
from subscription.models import Subscription


class EbouticTest(TestCase):
    def setUp(self):
        call_command("populate")
        self.skia = User.objects.filter(username="skia").first()
        self.subscriber = User.objects.filter(username="subscriber").first()
        self.old_subscriber = User.objects.filter(username="old_subscriber").first()
        self.public = User.objects.filter(username="public").first()
        self.barbar = Product.objects.filter(code="BARB").first()
        self.refill = Product.objects.filter(code="15REFILL").first()
        self.cotis = Product.objects.filter(code="1SCOTIZ").first()
        self.eboutic = Counter.objects.filter(name="Eboutic").first()

    def generate_bank_valid_answer_from_page_content(self, content):
        content = str(content)
        basket_id = re.search(r"PBX_CMD\" value=\"(\d*)\"", content).group(1)
        amount = re.search(r"PBX_TOTAL\" value=\"(\d*)\"", content).group(1)
        query = "Amount=%s&BasketID=%s&Auto=42&Error=00000" % (amount, basket_id)
        with open("./eboutic/tests/private_key.pem") as f:
            PRIVKEY = f.read()
        with open("./eboutic/tests/public_key.pem") as f:
            settings.SITH_EBOUTIC_PUB_KEY = f.read()
        privkey = crypto.load_privatekey(crypto.FILETYPE_PEM, PRIVKEY)
        sig = crypto.sign(privkey, query.encode("utf-8"), "sha1")
        b64sig = base64.b64encode(sig).decode("ascii")

        url = reverse("eboutic:etransation_autoanswer") + "?%s&Sig=%s" % (
            query,
            urllib.parse.quote_plus(b64sig),
        )
        response = self.client.get(url)
        return response

    def get_empty_basket(self):
        basket = Basket.objects.create(user=self.subscriber)
        session = self.client.session
        session["basket_id"] = basket.id
        session.save()
        return basket

    def get_busy_basket(self):
        """
        Create and return a basket with 3 barbar and 1 cotis in it.
        Edit the client session to store the basket id in it
        """
        basket = self.get_empty_basket()
        basket.add_product(self.barbar, 3)
        basket.add_product(self.cotis)
        return basket

    def get_simple_basket(self):
        """
        Create and return a basket with 1 barbar in it.
        Edit the client session to store the basket id in it
        """
        basket = self.get_empty_basket()
        basket.add_product(self.barbar)
        return basket

    def get_refill_basket(self):
        """
        Create and return a basket with 1 refill worth 15€ in it
        Edit the client session to store the basket id in it
        """
        basket = self.get_empty_basket()
        basket.add_product(self.refill)
        return basket

    def get_cotis_basket(self):
        basket = self.get_empty_basket()
        basket.add_product(self.cotis)
        return basket


class EbouticApiTest(EbouticTest):
    """
    Test class that tests the views coming from `api.py`
    """

    def test_user_logged_out_add_product(self):
        kwargs = {"product_id": self.barbar.id}
        res = self.client.post(reverse("eboutic:add_product", kwargs=kwargs))
        self.assertEqual(res.status_code, 302)

    def test_user_logged_out_remove_product(self):
        kwargs = {"product_id": self.barbar.id}
        res = self.client.post(reverse("eboutic:remove_product", kwargs=kwargs))
        self.assertEqual(res.status_code, 302)

    def test_user_logged_out_clear_basket(self):
        res = self.client.post(reverse("eboutic:clear_basket"))
        self.assertEqual(res.status_code, 302)

    def test_add_product_with_sith_account_empty_basket(self):
        self.client.login(username="subscriber", password="plop")
        self.assertFalse(Basket.objects.filter(user=self.subscriber).exists())

        kwargs = {"product_id": self.barbar.id}
        barbar_json = json.dumps(
            {
                "total": float(self.barbar.selling_price),
                "items": [{"product_id": self.barbar.id, "quantity": 1}],
            }
        )
        res = self.client.post(reverse("eboutic:add_product", kwargs=kwargs))
        baskets = Basket.objects.filter(user=self.subscriber)

        # test that the basket has been created with the right items
        self.assertTrue(baskets.exists())
        basket = baskets.first()
        self.assertEqual(basket.id, self.client.session["basket_id"])
        self.assertEqual(basket.items.count(), 1)
        self.assertEqual(basket.items.first().quantity, 1)
        self.assertEqual(basket.items.first().product_id, self.barbar.id)

        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(barbar_json, res.json())

    def test_add_product_with_sith_account_existing_basket(self):
        self.client.login(username="subscriber", password="plop")
        # the initial basket contains 1 cotis and 3 barbar
        basket = self.get_busy_basket()
        expected_session_basket_id = self.client.session["basket_id"]
        nb_baskets = Basket.objects.filter(user=self.subscriber).count()

        total_price = self.barbar.selling_price * 4 + self.cotis.selling_price
        expected = {
            "total": float(total_price),
            "items": [
                {"product_id": self.barbar.id, "quantity": 4},
                {"product_id": self.cotis.id, "quantity": 1},
            ],
        }
        kwargs = {"product_id": self.barbar.id}
        res = self.client.post(reverse("eboutic:add_product", kwargs=kwargs))

        new_nb_baskets = Basket.objects.filter(user=self.subscriber).count()
        self.assertEqual(
            new_nb_baskets,
            nb_baskets,
            msg="No new basket should be created if one is indicated in the session",
        )
        self.assertEqual(
            self.client.session["basket_id"],
            expected_session_basket_id,
            msg="The basket id in the session should not change",
        )
        self.assertEqual(basket.items.count(), 2)
        self.assertEqual(basket.items.get(product_id=self.barbar.id).quantity, 4)
        self.assertEqual(basket.items.get(product_id=self.cotis.id).quantity, 1)

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), expected)

    def test_add_invalid_product(self):
        self.client.login(username="subscriber", password="plop")
        basket = Basket.objects.create(user=self.subscriber)

        max_product_id = Product.objects.order_by("-id")[0].id
        kwargs = {"product_id": max_product_id + 1}
        res = self.client.post(reverse("eboutic:add_product", kwargs=kwargs))

        self.assertEqual(
            res.status_code,
            404,
            msg="Adding not existing product should result in a 404 response",
        )
        expected = {"error_msg": "This product does not exist"}
        self.assertEqual(res.json(), expected)
        self.assertEqual(
            basket.items.count(),
            0,
            msg="If the request is invalid, add nothing in the basket",
        )

    def test_remove_product(self):
        self.client.login(username="subscriber", password="plop")
        # the initial basket contains 1 cotis and 3 barbar
        basket = self.get_busy_basket()

        expected_session_basket_id = self.client.session["basket_id"]
        nb_baskets = Basket.objects.filter(user=self.subscriber).count()

        total_price = self.barbar.selling_price * 2 + self.cotis.selling_price
        expected_json = json.dumps(
            {
                "total": float(total_price),
                "items": [
                    {"product_id": self.barbar.id, "quantity": 2},
                    {"product_id": self.cotis.id, "quantity": 1},
                ],
            }
        )
        kwargs = {"product_id": self.barbar.id}
        res = self.client.post(reverse("eboutic:remove_product", kwargs=kwargs))

        new_nb_baskets = Basket.objects.filter(user=self.subscriber).count()
        self.assertEqual(
            new_nb_baskets,
            nb_baskets,
            msg="No new basket should be created if one is indicated in the session",
        )
        self.assertEqual(
            self.client.session["basket_id"],
            expected_session_basket_id,
            msg="The basket id in the session should not change",
        )
        self.assertEqual(basket.items.count(), 2)
        self.assertEqual(basket.items.get(product_id=self.barbar.id).quantity, 2)
        self.assertEqual(basket.items.get(product_id=self.cotis.id).quantity, 1)

        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(expected_json, res.json())

    def test_clear_basket(self):
        self.client.login(username="subscriber", password="plop")
        basket = self.get_busy_basket()

        nb_baskets = Basket.objects.filter(user=self.subscriber).count()

        res = self.client.post(reverse("eboutic:clear_basket"))
        new_nb_baskets = Basket.objects.filter(user=self.subscriber).count()
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            new_nb_baskets, nb_baskets,
            msg="Clearing the basket should not delete it",
        )
        basket = Basket.objects.get(id=basket.id)
        self.assertEqual(
            basket.get_total(), 0,
            msg="Total price should be equat to 0"
        )
        self.assertEqual(
            basket.items.count(), 0,
            msg="The basket should be empty"
        )

    def test_clear_non_existing_basket(self):
        # we register no basket in the session
        self.client.login(username="subscriber", password="plop")
        res = self.client.post(reverse("eboutic:clear_basket"))
        self.assertEqual(res.status_code, 404)


class EbouticViewTest(EbouticTest):
    def validate_basket(self):
        self.client.login(username="subscriber", password="plop")
        self.subscriber.customer.amount = 100  # give money before test
        self.subscriber.customer.save()
        self.get_busy_basket()
        response = self.client.post(reverse("eboutic:command"))
        res_content = "".join(str(response.content).split())
        self.assertTrue(
            "<tbody><tr><td>Barbar</td><td>3</td><td>1.70€</td></tr>"
            "<tr><td>Cotis1semestre</td><td>1</td><td>15.00€</td></tr></tbody>"
            in res_content
        )
        self.assertTrue(
            "<strong>Valeurdupanier:20.10€</strong><br>Soldeactuel:"
            "<strong>100.00€</strong><br>Solderestant:<strong>79.90€</strong>"
            in res_content
        )

    def test_buy_with_sith_account(self):
        self.client.login(username="subscriber", password="plop")
        self.subscriber.customer.amount = 100  # give money before test
        self.subscriber.customer.save()
        basket = self.get_busy_basket()
        amount = basket.get_total()
        response = self.client.post(
            reverse("eboutic:pay_with_sith"),
            {"action": "pay_with_sith_account"}
        )
        self.assertTrue(
            "Le paiement a \\xc3\\xa9t\\xc3\\xa9 effectu\\xc3\\xa9\\n"
            in str(response.content)
        )
        new_balance = Customer.objects.get(user=self.subscriber).amount
        self.assertEqual(float(new_balance), 100 - amount)

    def test_buy_with_sith_account_no_money(self):
        self.client.login(username="subscriber", password="plop")
        basket = self.get_busy_basket()
        initial_money = basket.get_total() - 1
        self.subscriber.customer.amount = initial_money
        self.subscriber.customer.save()
        response = self.client.post(
            reverse("eboutic:pay_with_sith"),
            {"action": "pay_with_sith_account"}
        )
        self.assertTrue(
            "Le paiement a \\xc3\\xa9chou\\xc3\\xa9"
            in str(response.content)
        )
        new_balance = Customer.objects.get(user=self.subscriber).amount
        self.assertEqual(float(new_balance), initial_money)

    def test_buy_simple_product_with_credit_card(self):
        self.client.login(username="subscriber", password="plop")
        self.get_simple_basket()
        response = self.client.post(reverse("eboutic:command"))
        response = self.generate_bank_valid_answer_from_page_content(response.content)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(response.content.decode("utf-8") == "")

        selling = Selling.objects \
            .filter(customer=self.subscriber.customer) \
            .order_by("-date") \
            .first()
        self.assertEqual(selling.payment_method, "CARD")
        self.assertEqual(selling.quantity, 1)
        self.assertEqual(selling.unit_price, self.barbar.selling_price)
        self.assertEqual(selling.counter.type, "EBOUTIC")
        self.assertEqual(selling.product, self.barbar)

    def test_alter_basket_with_credit_card(self):
        self.client.login(username="subscriber", password="plop")
        self.get_simple_basket()
        response = self.client.post(reverse("eboutic:command"))
        self.client.post(  # alter response
            reverse("eboutic:main"),
            {"action": "add_product", "product_id": self.barbar.id},
        )
        response = self.generate_bank_valid_answer_from_page_content(response.content)
        self.assertEqual(response.status_code, 500)
        self.assertIn(
            "Basket processing failed with error: SuspiciousOperation('Basket total and amount do not match'",
            response.content.decode("utf-8"),
        )

    def test_buy_refill_product_with_credit_card(self):
        self.client.login(username="subscriber", password="plop")
        self.get_refill_basket()
        # basket contains 1 refill item worth 15€
        initial_balance = self.subscriber.customer.amount
        response = self.client.post(reverse("eboutic:command"))

        response = self.generate_bank_valid_answer_from_page_content(response.content)
        self.assertTrue(response.status_code == 200)
        self.assertTrue(response.content.decode("utf-8") == "")
        new_balance = Customer.objects.get(user=self.subscriber).amount
        self.assertEqual(new_balance, initial_balance + 15)
