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
from counter.models import Product, Counter
from eboutic.models import Basket


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

    def get_busy_basket(self):
        """
        Return a basket with 3 barbar and 1 cotis in it.
        Edit the client session to store the basket id in it
        """
        basket = Basket.objects.create(user=self.subscriber)
        session = self.client.session
        session["basket_id"] = basket.id
        session.save()

        basket.add_product(self.barbar, 3)
        basket.add_product(self.cotis)
        return basket


class EbouticApiTest(EbouticTest):
    """
    Test class that tests the views coming from `api.py`
    """

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
        expected_json = json.dumps(
            {
                "total": float(total_price),
                "items": [
                    {"product_id": self.barbar.id, "quantity": 4},
                    {"product_id": self.cotis.id, "quantity": 1},
                ],
            }
        )
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
        self.assertJSONEqual(expected_json, res.json())

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
        self.assertJSONEqual(json.dumps({}), res.json())
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
