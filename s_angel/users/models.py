from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):

    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    # First and last name do not cover name patterns around the globe
    name = models.CharField(_("Name of User"), blank=True, max_length=255)
    username = models.CharField(blank=True, max_length=255)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    weight = models.IntegerField(_("User Weight"), default=1)
    generation = models.PositiveIntegerField(default=21, verbose_name="기수")
    can_view_accounting = models.BooleanField(default=False, verbose_name="회계 열람 권한")

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})
