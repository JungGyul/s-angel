import hashlib
import logging
import time

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import (
    CurrentPasswordVerifyForm,
    CustomSetPasswordForm,
    PasswordResetVerifyForm,
    SimpleUserSignupForm,
    UserProfileChangeForm,
)

User = get_user_model()
RESET_TIMEOUT = 600
RESET_MAX_ATTEMPTS = 5
logger = logging.getLogger(__name__)


def _clear_password_reset(session):
    for key in ('reset_user_id', 'reset_issued_at', 'reset_auth_hash',
                'reset_change_attempts', 'reset_authenticated_user_id', 'password_reset_grant'):
        session.pop(key, None)


def _claim_reset_attempt(scope, value):
    """Claim one of five slots in a ten-minute window across workers."""
    window = int(time.time() // RESET_TIMEOUT)
    digest = hashlib.sha256(value.encode('utf-8')).hexdigest()
    # Never reuse expired keys: DatabaseCache.add may update an expired row
    # without locking it. New window keys use its unique INSERT instead.
    try:
        for slot in range(RESET_MAX_ATTEMPTS):
            if cache.add(f'password-reset:{scope}:{digest}:{window}:{slot}', True, RESET_TIMEOUT):
                return True
    except Exception:
        # A missing or unavailable shared store must not disable the limiter.
        logger.exception('Password reset rate-limit cache unavailable')
    return False


@require_http_methods(["GET", "POST"])
def password_reset_verify(request):
    data = request.POST if request.method == "POST" else None
    if request.user.is_authenticated:
        form = CurrentPasswordVerifyForm(request.user, data)
    else:
        form = PasswordResetVerifyForm(data)
    if request.method == "POST":
        _clear_password_reset(request.session)
        now = time.time()
        username = request.user.username if request.user.is_authenticated else request.POST.get('username', '')
        username = User.normalize_username(username.strip()).casefold()
        ip_allowed = _claim_reset_attempt('ip', request.META.get('REMOTE_ADDR', 'unknown'))
        username_allowed = ip_allowed and _claim_reset_attempt('username', username)
        if not (ip_allowed and username_allowed):
            form.add_error(None, "시도 횟수를 초과했습니다. 10분 후 다시 시도할 수 있습니다.")
        elif form.is_valid():
            user = form.cleaned_data["user"]
            request.session.cycle_key()
            request.session["reset_user_id"] = user.pk
            request.session["reset_issued_at"] = now
            request.session["reset_auth_hash"] = user.get_session_auth_hash()
            request.session["reset_change_attempts"] = 0
            if request.user.is_authenticated:
                request.session['reset_authenticated_user_id'] = request.user.pk
            return redirect("users:password_reset_change")
    return render(request, "users/password_reset_verify.html", {"form": form})


@require_http_methods(["GET", "POST"])
def password_reset_change(request):
    user_id = request.session.get("reset_user_id")
    age = time.time() - request.session.get("reset_issued_at", 0)
    user = User.objects.filter(pk=user_id).first() if user_id else None
    authenticated_user_id = request.session.get('reset_authenticated_user_id')
    authenticated_grant = authenticated_user_id is not None
    if authenticated_grant:
        valid_binding = (
            request.user.is_authenticated
            and request.user.pk == authenticated_user_id == user_id
        )
    else:
        valid_binding = not request.user.is_authenticated
    if (
        user is None
        or not valid_binding
        or (not authenticated_grant and (user.is_staff or user.is_superuser))
        or not 0 <= age < RESET_TIMEOUT
        or request.session.get("reset_change_attempts", 0) >= RESET_MAX_ATTEMPTS
        or not constant_time_compare(
            request.session.get("reset_auth_hash", ""), user.get_session_auth_hash()
        )
    ):
        _clear_password_reset(request.session)
        return redirect("users:password_reset_verify")

    form = CustomSetPasswordForm(user, request.POST if request.method == "POST" else None)
    if request.method == "POST":
        request.session["reset_change_attempts"] = request.session.get("reset_change_attempts", 0) + 1
        if form.is_valid():
            _clear_password_reset(request.session)
            form.save()
            if authenticated_grant:
                update_session_auth_hash(request, user)
                messages.success(request, '비밀번호를 변경했습니다.')
                return redirect('users:profile_update')
            messages.success(request, '비밀번호를 재설정했습니다. 새 비밀번호로 로그인할 수 있습니다.')
            return redirect("users:main")
    return render(request, "users/password_reset_change.html", {"form": form})


def signup(request):
    if request.user.is_authenticated:
        return redirect('applications:dashboard')
    if request.method == "POST":
        
        form = SimpleUserSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)  # DB에 바로 저장하지 않고
            
            # ▼▼▼ 핵심 변경사항 ▼▼▼
            # 1. 새로 가입한 사용자를 '비활성' 상태로 설정합니다.
            user.is_active = False
            user.save()  # 이제 사용자 정보를 저장합니다.

            # 2. 바로 로그인시키는 대신, 안내 메시지를 보여주고 로그인 페이지로 보냅니다.
            message = (
                "회원가입 신청이 완료되었습니다. "
                "운영진의 승인 후 로그인할 수 있습니다."
            )
            messages.warning(request, message)
            return redirect('users:main') # 로그인 페이지(main)로 리다이렉트
            
        else:
            # 폼 유효성 검사 실패 시 에러와 함께 폼을 다시 표시
            return render(request, 'users/signup.html', {'form': form, 'errors': form.errors})
    else:
        form = SimpleUserSignupForm()
        
        # ▼▼▼ messages 대신 context 변수로 직접 전달합니다. ▼▼▼
        context = {
            'form': form,
            'info_message': '에스엔젤 부원만 회원가입할 수 있습니다.'
        }
        return render(request, 'users/signup.html', context)

    return render(request, 'users/signup.html', {'form': form})

@require_http_methods(["GET", "POST"])
def main(request):
    if request.user.is_authenticated:
        return redirect('applications:dashboard')
    if request.method == 'GET':
        return render(request, 'users/main.html')

    elif request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # ▼▼▼ 로그인 시도 시 계정 활성화 여부 체크 ▼▼▼
        user = authenticate(request, username=username, password=password)
        if user is not None:
            # is_active가 True일 때만 로그인 성공
            if user.is_active:
                login(request, user)
                next_url = request.POST.get("next") or request.GET.get("next")
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return HttpResponseRedirect(next_url)
                return redirect('applications:dashboard')
            else:
                # 계정이 비활성 상태일 때
                return render(request, 'users/main.html', {'error': '운영진의 승인 대기 중인 계정입니다.'})
        else:
            pending_user = User.objects.filter(username=username, is_active=False).first()
            if pending_user is not None and password and pending_user.check_password(password):
                return render(request, 'users/main.html', {
                    'error': '운영진의 승인 대기 중인 계정입니다.',
                })
            return render(request, 'users/main.html', {'error': '아이디 또는 비밀번호가 올바르지 않습니다.'})

def legacy_account_redirect(request):
    """Route unused allauth screens to the site's account entry point."""
    return redirect('applications:dashboard' if request.user.is_authenticated else 'users:main')


def legacy_password_redirect(request):
    """Use the site's reset/change flow for every legacy password URL."""
    return redirect('users:password_reset_verify')


@login_required
def profile_update(request):
    if request.method == 'POST':
        form = UserProfileChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.save(update_fields=list(form.fields))
            messages.success(request, '내 정보를 수정했습니다.')
            return redirect('applications:dashboard')
    else:
        form = UserProfileChangeForm(instance=request.user)
        
    return render(request, 'users/profile_update.html', {'form': form})


