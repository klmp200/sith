# -*- coding:utf-8 -*
#
# Copyright 2023
# - Skia <skia@hya.sk>
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

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from core.models import User
from galaxy.models import Galaxy


class GalaxyTestModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.get(username="root")
        cls.skia = User.objects.get(username="skia")
        cls.sli = User.objects.get(username="sli")
        cls.krophil = User.objects.get(username="krophil")
        cls.richard = User.objects.get(username="rbatsbak")
        cls.subscriber = User.objects.get(username="subscriber")
        cls.public = User.objects.get(username="public")
        cls.com = User.objects.get(username="comunity")

    def test_user_self_score(self):
        """
        Test that individual user scores are correct
        """
        with self.assertNumQueries(8):
            assert Galaxy.compute_user_score(self.root) == 9
            assert Galaxy.compute_user_score(self.skia) == 10
            assert Galaxy.compute_user_score(self.sli) == 8
            assert Galaxy.compute_user_score(self.krophil) == 2
            assert Galaxy.compute_user_score(self.richard) == 10
            assert Galaxy.compute_user_score(self.subscriber) == 8
            assert Galaxy.compute_user_score(self.public) == 8
            assert Galaxy.compute_user_score(self.com) == 1

    def test_users_score(self):
        """
        Test on the default dataset generated by the `populate` command
        that the relation scores are correct
        """
        expected_scores = {
            "krophil": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "public": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "rbatsbak": {"clubs": 100, "family": 0, "pictures": 0, "score": 100},
                "subscriber": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
            },
            "public": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0}
            },
            "rbatsbak": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "public": {"clubs": 0, "family": 366, "pictures": 0, "score": 366},
                "subscriber": {"clubs": 0, "family": 366, "pictures": 0, "score": 366},
            },
            "root": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "krophil": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "public": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "rbatsbak": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "skia": {"clubs": 0, "family": 732, "pictures": 0, "score": 732},
                "sli": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "subscriber": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
            },
            "skia": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "krophil": {"clubs": 114, "family": 0, "pictures": 2, "score": 116},
                "public": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "rbatsbak": {"clubs": 100, "family": 0, "pictures": 0, "score": 100},
                "sli": {"clubs": 0, "family": 366, "pictures": 4, "score": 370},
                "subscriber": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
            },
            "sli": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "krophil": {"clubs": 17, "family": 0, "pictures": 2, "score": 19},
                "public": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "rbatsbak": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "subscriber": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
            },
            "subscriber": {
                "comunity": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
                "public": {"clubs": 0, "family": 0, "pictures": 0, "score": 0},
            },
        }
        computed_scores = {}
        users = [
            self.root,
            self.skia,
            self.sli,
            self.krophil,
            self.richard,
            self.subscriber,
            self.public,
            self.com,
        ]

        with self.assertNumQueries(100):
            while len(users) > 0:
                user1 = users.pop(0)
                for user2 in users:
                    score = Galaxy.compute_users_score(user1, user2)
                    u1 = computed_scores.get(user1.username, {})
                    u1[user2.username] = {
                        "score": sum(score),
                        "family": score.family,
                        "pictures": score.pictures,
                        "clubs": score.clubs,
                    }
                    computed_scores[user1.username] = u1

        self.maxDiff = None  # Yes, we want to see the diff if any
        self.assertDictEqual(expected_scores, computed_scores)

    def test_rule(self):
        """
        Test on the default dataset generated by the `populate` command
        that the number of queries to rule the galaxy is stable.
        """
        galaxy = Galaxy.objects.create()
        with self.assertNumQueries(58):
            galaxy.rule(0)  # We want everybody here


@pytest.mark.slow
class GalaxyTestView(TestCase):
    @classmethod
    def setUpTestData(cls):
        """
        Generate a plausible Galaxy once for every test
        """
        call_command("generate_galaxy_test_data", "-v", "0")
        galaxy = Galaxy.objects.create()
        galaxy.rule(26)  # We want a fast test
        cls.root = User.objects.get(username="root")

    def test_page_is_citizen(self):
        """
        Test that users can access the galaxy page of users who are citizens
        """
        self.client.force_login(self.root)
        user = User.objects.get(last_name="n°500")
        response = self.client.get(reverse("galaxy:user", args=[user.id]))
        self.assertContains(
            response,
            f'<a onclick="focus_node(get_node_from_id({user.id}))">Reset on {user}</a>',
            status_code=200,
        )

    def test_page_not_citizen(self):
        """
        Test that trying to access the galaxy page of a user who is not
        citizens return a 404
        """
        self.client.force_login(self.root)
        user = User.objects.get(last_name="n°1")
        response = self.client.get(reverse("galaxy:user", args=[user.id]))
        assert response.status_code == 404

    def test_full_galaxy_state(self):
        """
        Test on the more complex dataset generated by the `generate_galaxy_test_data`
        command that the relation scores are correct, and that the view exposes the
        right data.
        """
        self.client.force_login(self.root)
        response = self.client.get(reverse("galaxy:data"))
        state = response.json()

        galaxy_dir = Path(__file__).parent

        # Dump computed state, either for easier debugging, or to copy as new reference if changes are legit
        (galaxy_dir / "test_galaxy_state.json").write_text(json.dumps(state))

        assert state == json.loads((galaxy_dir / "ref_galaxy_state.json").read_text())
