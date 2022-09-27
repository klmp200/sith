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


class EbouticApiTest(EbouticTest):
    """
    Test class that tests the views coming from `api.py`
    """

    def test_add_product_with_sith_account_empty_basket(self):
        self.client.login(username="subscriber", password="plop")
        self.assertFalse(Basket.objects.filter(user=self.subscriber).exists())

        kwargs = {"product_id": self.barbar.id}
        barbar_json = json.dumps({
            "total": float(self.barbar.selling_price),
            "items": [
                {"product_id": self.barbar.id, "quantity": 1}
            ]
        })
        res = self.client.post(reverse('eboutic:add_product', kwargs=kwargs))
        baskets = Basket.objects.filter(user=self.subscriber)

        # test that the basket has been created with the right items
        self.assertTrue(baskets.exists())
        basket = baskets.first()
        self.assertEqual(basket.id, self.client.session["basket_id"])
        self.assertEqual(basket.items.count(), 1)
        self.assertEqual(basket.items.first().product_id, self.barbar.id)

        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(barbar_json, res.json())

    def test_add_product_with_sith_account_existing_basket(self):
        self.client.login(username="subscriber", password="plop")
        basket = Basket.objects.create(user=self.subscriber)
        self.client.session["product_id"] = basket.id
        expected_session_product_id = self.client.session["product_id"]
        basket.add_product(self.barbar, 3)
        basket.add_product(self.cotis)
        nb_baskets = Basket.objects.filter(user=self.subscriber).count()

        kwargs = {"product_id": self.barbar.id}
        total_price = self.barbar.selling_price * 4 + self.cotis.selling_price
        expected_json = json.dumps({
            "total": float(total_price),
            "items": [
                {"product_id": self.barbar.id, "quantity": 4},
                {"product_id": self.cotis.id, "quantity": 1}
            ]
        })
        res = self.client.post(reverse('eboutic:add_product', kwargs=kwargs))

        new_nb_baskets = Basket.objects.filter(user=self.subscriber).count()
        self.assertEqual(new_nb_baskets, nb_baskets)
        self.assertEqual(self.client.session["basket_id"], expected_session_product_id)
        self.assertEqual(basket.items.count(), 5)
        self.assertEqual(basket.items.filter(product_id=self.barbar.id).count(), 4)
        self.assertEqual(basket.items.filter(product_id=self.cotis.id).count(), 1)

        self.assertEqual(res.status_code, 200)
        self.assertJSONEqual(expected_json, res.json())

# def test_buy_simple_product_with_sith_account(self):
#     self.client.login(username="subscriber", password="plop")
#     Refilling(
#         amount=10,
#         counter=self.eboutic,
#         operator=self.skia,
#         customer=self.subscriber.customer,
#     ).save()
#     response = self.client.post(
#         reverse("eboutic:main"),
#         {"action": "add_product", "product_id": self.barbar.id},
#     )
#     self.assertTrue(
#         '<input type="hidden" name="action" value="add_product">\\n'
#         '    <button type="submit" name="product_id" value="4"> + </button>\\n'
#         "</form>\\n Barbar: 1.70 \\xe2\\x82\\xac</li>" in str(response.content)
#     )
#     response = self.client.post(reverse("eboutic:command"))
#     self.assertTrue(
#         "<tr>\\n                <td>Barbar</td>\\n                <td>1</td>\\n"
#         "                <td>1.70 \\xe2\\x82\\xac</td>\\n            </tr>"
#         in str(response.content)
#     )
#     response = self.client.post(
#         reverse("eboutic:pay_with_sith"), {"action": "pay_with_sith_account"}
#     )
#     self.assertTrue(
#         "Le paiement a \\xc3\\xa9t\\xc3\\xa9 effectu\\xc3\\xa9\\n"
#         in str(response.content)
#     )
#     response = self.client.get(
#         reverse(
#             "core:user_account_detail",
#             kwargs={
#                 "user_id": self.subscriber.id,
#                 "year": datetime.now().year,
#                 "month": datetime.now().month,
#             },
#         )
#     )
#     self.assertTrue(
#         'class="selected_tab">Compte (8.30 \\xe2\\x82\\xac)</a>'
#         in str(response.content)
#     )
#     self.assertTrue(
#         '<td>Eboutic</td>\\n        <td><a href="/user/3/">Subscribed User</a></td>\\n'
#         "        <td>Barbar</td>\\n        <td>1</td>\\n        <td>1.70 \\xe2\\x82\\xac</td>\\n"
#         "        <td>Compte utilisateur</td>" in str(response.content)
#     )
#
# def test_buy_simple_product_with_credit_card(self):
#     self.client.login(username="subscriber", password="plop")
#     response = self.client.post(
#         reverse("eboutic:main"),
#         {"action": "add_product", "product_id": self.barbar.id},
#     )
#     self.assertTrue(
#         '<input type="hidden" name="action" value="add_product">\\n'
#         '    <button type="submit" name="product_id" value="4"> + </button>\\n'
#         "</form>\\n Barbar: 1.70 \\xe2\\x82\\xac</li>" in str(response.content)
#     )
#     response = self.client.post(reverse("eboutic:command"))
#     self.assertTrue(
#         "<tr>\\n                <td>Barbar</td>\\n                <td>1</td>\\n"
#         "                <td>1.70 \\xe2\\x82\\xac</td>\\n            </tr>"
#         in str(response.content)
#     )
#
#     response = self.generate_bank_valid_answer_from_page_content(response.content)
#     self.assertTrue(response.status_code == 200)
#     self.assertTrue(response.content.decode("utf-8") == "")
#
#     response = self.client.get(
#         reverse(
#             "core:user_account_detail",
#             kwargs={
#                 "user_id": self.subscriber.id,
#                 "year": datetime.now().year,
#                 "month": datetime.now().month,
#             },
#         )
#     )
#     self.assertTrue(
#         'class="selected_tab">Compte (0.00 \\xe2\\x82\\xac)</a>'
#         in str(response.content)
#     )
#     self.assertTrue(
#         '<td>Eboutic</td>\\n        <td><a href="/user/3/">Subscribed User</a></td>\\n'
#         "        <td>Barbar</td>\\n        <td>1</td>\\n        <td>1.70 \\xe2\\x82\\xac</td>\\n"
#         "        <td>Carte bancaire</td>" in str(response.content)
#     )
#
# def test_alter_basket_with_credit_card(self):
#     self.client.login(username="subscriber", password="plop")
#     response = self.client.post(
#         reverse("eboutic:main"),
#         {"action": "add_product", "product_id": self.barbar.id},
#     )
#     self.assertTrue(
#         '<input type="hidden" name="action" value="add_product">\\n'
#         '    <button type="submit" name="product_id" value="4"> + </button>\\n'
#         "</form>\\n Barbar: 1.70 \\xe2\\x82\\xac</li>" in str(response.content)
#     )
#     response = self.client.post(reverse("eboutic:command"))
#     self.assertTrue(
#         "<tr>\\n                <td>Barbar</td>\\n                <td>1</td>\\n"
#         "                <td>1.70 \\xe2\\x82\\xac</td>\\n            </tr>"
#         in str(response.content)
#     )
#
#     response_altered = self.client.post(
#         reverse("eboutic:main"),
#         {"action": "add_product", "product_id": self.barbar.id},
#     )
#     self.assertTrue(
#         '<input type="hidden" name="action" value="add_product">\\n'
#         '    <button type="submit" name="product_id" value="4"> + </button>\\n'
#         "</form>\\n Barbar: 3.40 \\xe2\\x82\\xac</li>"
#         in str(response_altered.content)
#     )
#
#     response = self.generate_bank_valid_answer_from_page_content(response.content)
#     self.assertEqual(response.status_code, 500)
#     self.assertIn(
#         "Basket processing failed with error: SuspiciousOperation('Basket total and amount do not match'",
#         response.content.decode("utf-8"),
#     )
#
# def test_buy_refill_product_with_credit_card(self):
#     self.client.login(username="subscriber", password="plop")
#     response = self.client.post(
#         reverse("eboutic:main"),
#         {"action": "add_product", "product_id": self.refill.id},
#     )
#     self.assertTrue(
#         '<input type="hidden" name="action" value="add_product">\\n'
#         '    <button type="submit" name="product_id" value="3"> + </button>\\n'
#         "</form>\\n Rechargement 15 \\xe2\\x82\\xac: 15.00 \\xe2\\x82\\xac</li>"
#         in str(response.content)
#     )
#     response = self.client.post(reverse("eboutic:command"))
#     self.assertTrue(
#         "<tr>\\n                <td>Rechargement 15 \\xe2\\x82\\xac</td>\\n                <td>1</td>\\n"
#         "                <td>15.00 \\xe2\\x82\\xac</td>\\n            </tr>"
#         in str(response.content)
#     )
#
#     response = self.generate_bank_valid_answer_from_page_content(response.content)
#     self.assertTrue(response.status_code == 200)
#     self.assertTrue(response.content.decode("utf-8") == "")
#
#     response = self.client.get(
#         reverse(
#             "core:user_account_detail",
#             kwargs={
#                 "user_id": self.subscriber.id,
#                 "year": datetime.now().year,
#                 "month": datetime.now().month,
#             },
#         )
#     )
#     self.assertTrue(
#         'class="selected_tab">Compte (15.00 \\xe2\\x82\\xac)</a>'
#         in str(response.content)
#     )
#     self.assertTrue(
#         "<td>\\n            <ul>\\n                \\n                "
#         "<li>1 x Rechargement 15 \\xe2\\x82\\xac - 15.00 \\xe2\\x82\\xac</li>\\n"
#         "                \\n            </ul>\\n        </td>\\n"
#         "        <td>15.00 \\xe2\\x82\\xac</td>" in str(response.content)
#     )
#
# def test_buy_subscribe_product_with_credit_card(self):
#     self.client.login(username="old_subscriber", password="plop")
#     response = self.client.get(
#         reverse("core:user_profile", kwargs={"user_id": self.old_subscriber.id})
#     )
#     self.assertTrue("Non cotisant" in str(response.content))
#     response = self.client.post(
#         reverse("eboutic:main"),
#         {"action": "add_product", "product_id": self.cotis.id},
#     )
#     self.assertTrue(
#         '<input type="hidden" name="action" value="add_product">\\n'
#         '    <button type="submit" name="product_id" value="1"> + </button>\\n'
#         "</form>\\n Cotis 1 semestre: 15.00 \\xe2\\x82\\xac</li>"
#         in str(response.content)
#     )
#     response = self.client.post(reverse("eboutic:command"))
#     self.assertTrue(
#         "<tr>\\n                <td>Cotis 1 semestre</td>\\n                <td>1</td>\\n"
#         "                <td>15.00 \\xe2\\x82\\xac</td>\\n            </tr>"
#         in str(response.content)
#     )
#
#     response = self.generate_bank_valid_answer_from_page_content(response.content)
#     self.assertTrue(response.status_code == 200)
#     self.assertTrue(response.content.decode("utf-8") == "")
#
#     response = self.client.get(
#         reverse(
#             "core:user_account_detail",
#             kwargs={
#                 "user_id": self.old_subscriber.id,
#                 "year": datetime.now().year,
#                 "month": datetime.now().month,
#             },
#         )
#     )
#     self.assertTrue(
#         'class="selected_tab">Compte (0.00 \\xe2\\x82\\xac)</a>'
#         in str(response.content)
#     )
#     self.assertTrue(
#         "<td>\\n            <ul>\\n                \\n                "
#         "<li>1 x Cotis 1 semestre - 15.00 \\xe2\\x82\\xac</li>\\n"
#         "                \\n            </ul>\\n        </td>\\n"
#         "        <td>15.00 \\xe2\\x82\\xac</td>" in str(response.content)
#     )
#     response = self.client.get(
#         reverse("core:user_profile", kwargs={"user_id": self.old_subscriber.id})
#     )
#     self.assertTrue("Cotisant jusqu\\'au" in str(response.content))
