# Generated by Django 2.2.6 on 2019-11-14 15:10

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0033_auto_20191006_0049"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationLog",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("date", models.DateTimeField(auto_now_add=True, verbose_name="date")),
                ("label", models.CharField(max_length=255, verbose_name="label")),
                (
                    "operation_type",
                    models.CharField(
                        choices=[
                            ("SELLING_DELETION", "Selling deletion"),
                            ("REFILLING_DELETION", "Refilling deletion"),
                        ],
                        max_length=40,
                        verbose_name="operation type",
                    ),
                ),
                (
                    "operator",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
