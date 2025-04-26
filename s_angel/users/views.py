from django.shortcuts import render
from django.contrib.auth import authenticate, login
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

User = get_user_model()
from .forms import SimpleUserSignupForm



def signup(request):
    if request.method == "POST":
        form = SimpleUserSignupForm(request.POST)
        if form.is_valid():
            user = form.save()  # 사용자 저장

            # 로그인
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']  # password1을 사용하여 인증
            user = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                return redirect('applications:dashboard')  # 로그인 후 대시보드로 이동
            else:
                return render(request, 'users/signup.html', {'form': form, 'error': '로그인에 실패했습니다.'})
        else:
            print(form.errors)
            return render(request, 'users/signup.html')
    else:
        form = SimpleUserSignupForm()

    return render(request, 'users/signup.html', {'form': form})


def main(request):
    if request.method == 'GET':
        return render(request, 'users/main.html')

    elif request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('applications:dashboard')
        else:
            return render(request, 'users/main.html', {'error': 'Invalid credentials'})