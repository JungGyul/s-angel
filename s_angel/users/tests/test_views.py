from http import HTTPStatus

import pytest
from django.conf import settings
from django.urls import reverse
from pytest_django.asserts import assertRedirects

from s_angel.users.models import User

pytestmark = pytest.mark.django_db
TEST_PASSWORD = "test-login-password"  # noqa: S105
UPDATED_GENERATION = 22


def test_main_page(client):
    response = client.get(reverse("users:main"))

    assert response.status_code == HTTPStatus.OK


def test_main_login_redirects_to_dashboard(client, user: User):
    user.set_password(TEST_PASSWORD)
    user.is_active = True
    user.save(update_fields=["password", "is_active"])

    response = client.post(
        reverse("users:main"),
        {
            "username": user.username,
            "password": TEST_PASSWORD,
        },
    )

    assertRedirects(
        response,
        reverse("applications:dashboard"),
        fetch_redirect_response=False,
    )


def test_profile_update_requires_login(client):
    response = client.get(reverse("users:profile_update"))

    expected_url = (
        f"{reverse(settings.LOGIN_URL)}?next={reverse('users:profile_update')}"
    )
    assertRedirects(
        response,
        expected_url,
        fetch_redirect_response=False,
    )


def test_profile_update(client, user: User):
    client.force_login(user)

    response = client.post(
        reverse("users:profile_update"),
        {
            "username": user.username,
            "name": "수정된 이름",
            "gender": "F",
            "generation": UPDATED_GENERATION,
        },
    )

    assertRedirects(
        response,
        reverse("applications:dashboard"),
        fetch_redirect_response=False,
    )
    user.refresh_from_db()
    assert user.name == "수정된 이름"
    assert user.gender == "F"
    assert user.generation == UPDATED_GENERATION


def test_inactive_login_shows_pending_only_with_correct_password(client, user):
    user.is_active = False
    user.set_password(TEST_PASSWORD)
    user.save(update_fields=['is_active', 'password'])
    url = reverse('users:main')
    response = client.post(url, {'username': user.username, 'password': TEST_PASSWORD})
    assert '승인 대기' in response.context['error']
    assert '_auth_user_id' not in client.session
    response = client.post(url, {'username': user.username, 'password': 'incorrect'})
    assert '승인 대기' not in response.context['error']


def test_signup_requests_approval_with_plain_warning(client):
    from django.contrib.messages import WARNING, get_messages
    response = client.post(reverse('users:signup'), {
        'username': 'new-pending-user', 'name': '새 부원', 'gender': 'F', 'generation': 22,
        'password1': 'new-safe-password-9184', 'password2': 'new-safe-password-9184',
    })
    assert response.status_code == 302
    assert not User.objects.get(username='new-pending-user').is_active
    message = list(get_messages(response.wsgi_request))[0]
    assert message.level == WARNING
    assert '<br>' not in str(message)


def test_profile_does_not_overwrite_concurrent_weight(client, user):
    from unittest.mock import patch
    from s_angel.users.forms import UserProfileChangeForm
    original_save = UserProfileChangeForm.save
    def concurrent_save(form, *args, **kwargs):
        User.objects.filter(pk=form.instance.pk).update(weight=9)
        return original_save(form, *args, **kwargs)
    client.force_login(user)
    with patch.object(UserProfileChangeForm, 'save', concurrent_save):
        response = client.post(reverse('users:profile_update'), {
            'username': user.username, 'name': '수정된 이름', 'gender': 'F', 'generation': 22,
        })
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.weight == 9
    assert user.name == '수정된 이름'


def test_allauth_signup_is_closed_by_default(client, settings):
    from django.test import RequestFactory
    from s_angel.users.adapters import AccountAdapter, SocialAccountAdapter
    settings.ACCOUNT_ALLOW_REGISTRATION = False
    request = RequestFactory().get('/accounts/signup/')
    assert not AccountAdapter().is_open_for_signup(request)
    assert not SocialAccountAdapter().is_open_for_signup(request, None)
    before = User.objects.count()
    response = client.post(reverse('account_signup'), {
        'username': 'bypass-user', 'password1': 'new-safe-password-9184',
        'password2': 'new-safe-password-9184',
    })
    assert response.status_code == 302
    assert response.url == reverse('users:main')
    assert User.objects.count() == before


@pytest.mark.parametrize('view_name', ['users:main', 'users:signup'])
@pytest.mark.parametrize('method', ['get', 'post'])
def test_authenticated_account_entry_pages_return_home(client, user, view_name, method):
    client.force_login(user)
    before = User.objects.count()
    response = getattr(client, method)(reverse(view_name), {'username': 'unexpected-new-account'})
    assert response.status_code == 302
    assert response.url == reverse('applications:dashboard')
    assert User.objects.count() == before
    assert client.session['_auth_user_id'] == str(user.pk)


@pytest.mark.parametrize('path', [
    '/accounts/password/reset/', '/accounts/password/change/', '/accounts/password/set/',
    '/accounts/password/reset/done/', '/accounts/password/reset/key/done/',
    '/accounts/password/reset/key/abc-token/', '/accounts/password/reset/confirm/',
    '/accounts/password/reset/complete/',
])
@pytest.mark.parametrize('authenticated', [False, True])
def test_legacy_password_screens_use_site_flow(client, user, path, authenticated):
    if authenticated:
        client.force_login(user)
    response = client.get(path)
    assert response.status_code == 302
    assert response.url == reverse('users:password_reset_verify')


@pytest.mark.parametrize('path', [
    '/accounts/', '/accounts/login/', '/accounts/signup/', '/accounts/inactive/',
    '/accounts/email/', '/accounts/confirm-email/', '/accounts/confirm-email/example-key/',
    '/accounts/reauthenticate/', '/accounts/login/code/confirm/', '/accounts/3rdparty/signup/',
])
@pytest.mark.parametrize('authenticated', [False, True])
def test_legacy_account_screens_use_site_entry(client, user, path, authenticated):
    if authenticated:
        client.force_login(user)
    response = client.get(path)
    assert response.status_code == 302
    target = 'applications:dashboard' if authenticated else 'users:main'
    assert response.url == reverse(target)


@pytest.mark.parametrize('view_name', ['logout', 'account_logout'])
def test_custom_and_legacy_logout_end_session(client, user, view_name):
    client.force_login(user)
    url = reverse(view_name)
    assert client.get(url).status_code == 405
    assert client.session['_auth_user_id'] == str(user.pk)
    response = client.post(url)
    assert response.status_code == 302
    assert response.url == reverse('users:main')
    assert '_auth_user_id' not in client.session


def test_allauth_reverse_names_remain_available():
    assert reverse('account_login') == '/accounts/login/'
    assert reverse('account_signup') == '/accounts/signup/'
    assert reverse('account_reset_password') == '/accounts/password/reset/'
    assert reverse('account_reset_password_from_key', kwargs={'uidb36': 'abc', 'key': 'token'}) == '/accounts/password/reset/key/abc-token/'
