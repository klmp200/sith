from abc import ABC, abstractmethod

from django.core.exceptions import SuspiciousOperation
from django.shortcuts import redirect, render


class EbouticCookieError(ABC, Exception):
    @abstractmethod
    def get_redirection(self, request):
        pass


class CookieNegativeIndex(EbouticCookieError, SuspiciousOperation):
    def get_redirection(self, request):
        return render(request, "core/cheater.jinja")


class CookieImproperlyFormatted(EbouticCookieError):
    def get_redirection(self, request):
        return redirect("eboutic:main")


class CookieEmpty(EbouticCookieError):
    def get_redirection(self, request):
        return redirect("eboutic:main")
