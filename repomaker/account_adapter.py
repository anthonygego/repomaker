from allauth.account.adapter import DefaultAccountAdapter
from django.conf import settings


class RegistrationFilterAccountAdapter(DefaultAccountAdapter):

    def is_open_for_signup(self, request):
        return (not settings.SINGLE_USER_MODE) and settings.ALLOW_REGISTRATION


def context_processor(request):
    return {
        'ALLOW_REGISTRATION': (not settings.SINGLE_USER_MODE) and settings.ALLOW_REGISTRATION
    }
