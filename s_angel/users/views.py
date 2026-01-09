from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages  # messages 프레임워크 import
from .forms import PasswordResetVerifyForm, CustomSetPasswordForm





User = get_user_model()
from .forms import SimpleUserSignupForm, UserProfileChangeForm
from django.contrib.auth.decorators import login_required


def password_reset_verify(request):
    if request.method == "POST":
        form = PasswordResetVerifyForm(request.POST)
        if form.is_valid():
            # 확인 성공 시 세션에 유저 ID 저장 후 변경 페이지로
            request.session['reset_user_id'] = form.cleaned_data['user'].pk
            return redirect('users:password_reset_change')
    else:
        form = PasswordResetVerifyForm()
    return render(request, 'users/password_reset_verify.html', {'form': form})

def password_reset_change(request):
    user_id = request.session.get('reset_user_id')
    if not user_id:
        return redirect('users:password_reset_verify')
    
    user = get_object_or_404(User, pk=user_id)
    
    if request.method == "POST":
        form = CustomSetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            del request.session['reset_user_id']
            messages.success(request, "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해주세요.")
            return redirect('users:main')
    else:
        form = CustomSetPasswordForm(user)

    return render(request, 'users/password_reset_change.html', {'form': form})


def signup(request):
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
                "회원가입 신청이 완료되었습니다.<br>"
                "관리자의 승인 후 로그인이 가능합니다."
            )
            messages.info(request, message)
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

def main(request):
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
                return redirect('applications:dashboard')
            else:
                # 계정이 비활성 상태일 때
                return render(request, 'users/main.html', {'error': '아직 관리자의 승인을 받지 않은 계정입니다.'})
        else:
            # 아이디 또는 비밀번호가 틀렸을 때
            return render(request, 'users/main.html', {'error': '아이디 또는 비밀번호가 올바르지 않습니다.'})

@login_required
def profile_update(request):
    if request.method == 'POST':
        form = UserProfileChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, '프로필이 성공적으로 수정되었습니다.')
            return redirect('applications:dashboard')
    else:
        form = UserProfileChangeForm(instance=request.user)
        
    return render(request, 'users/profile_update.html', {'form': form})


