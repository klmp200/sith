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
from datetime import datetime

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

    def get_empty_basket(self, user):
        session = self.client.session
        basket = Basket.objects.create(user=user)
        session["basket_id"] = basket.id
        session.save()
        return basket

    def get_busy_basket(self, user):
        """
        Create and return a basket with 3 barbar and 1 cotis in it.
        Edit the client session to store the basket id in it
        """
        basket = self.get_empty_basket(user)
        basket.add_product(self.barbar, 3)
        basket.add_product(self.cotis)
        return basket

    def get_simple_basket(self, user):
        """
        Create and return a basket with 1 barbar in it.
        Edit the client session to store the basket id in it
        """
        basket = self.get_empty_basket(user)
        basket.add_product(self.barbar)
        return basket

    def get_refill_basket(self, user):
        """
        Create and return a basket with 1 refill worth 15€ in it
        Edit the client session to store the basket id in it
        """
        basket = self.get_empty_basket(user)
        basket.add_product(self.refill)
        return basket


class EbouticViewTest(EbouticTest):
    def test_buy_with_sith_account(self):
        self.client.login(username="subscriber", password="plop")
        self.subscriber.customer.amount = 100  # give money before test
        self.subscriber.customer.save()
        basket = self.get_busy_basket(self.subscriber)
        amount = basket.get_total()
        response = self.client.post(
            reverse("eboutic:pay_with_sith"), {"action": "pay_with_sith_account"}
        )
        self.assertTrue(
            "Le paiement a \\xc3\\xa9t\\xc3\\xa9 effectu\\xc3\\xa9\\n"
            in str(response.content)
        )
        new_balance = Customer.objects.get(user=self.subscriber).amount
        self.assertEqual(float(new_balance), 100 - amount)

    def test_buy_with_sith_account_no_money(self):
        self.client.login(username="subscriber", password="plop")
        basket = self.get_busy_basket(self.subscriber)
        initial_money = basket.get_total() - 1
        self.subscriber.customer.amount = initial_money
        self.subscriber.customer.save()
        response = self.client.post(
            reverse("eboutic:pay_with_sith"), {"action": "pay_with_sith_account"}
        )
        self.assertTrue(
            "Le paiement a \\xc3\\xa9chou\\xc3\\xa9" in str(response.content)
        )
        new_balance = Customer.objects.get(user=self.subscriber).amount
        self.assertEqual(float(new_balance), initial_money)
