# -*- coding: utf-8 -*-
# Generated by Django 1.11.24 on 2019-09-06 14:15
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("core", "0030_auto_20190704_1500")]

    operations = [
        migrations.AlterField(
            model_name="sithfile",
            name="is_folder",
            field=models.BooleanField(
                db_index=True, default=True, verbose_name="is folder"
            ),
        ),
        migrations.AlterField(
            model_name="sithfile",
            name="is_in_sas",
            field=models.BooleanField(
                db_index=True, default=False, verbose_name="is in the SAS"
            ),
        ),
    ]
