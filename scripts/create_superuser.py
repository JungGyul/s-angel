# scripts/create_superuser.py

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')  # 네 프로젝트 설정에 맞춰
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 's_angel1004')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'hinjghinjg12@naver.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin13981004')

if not User.objects.filter(username=username).exists():
    print('슈퍼유저 생성 중...')
    User.objects.create_superuser(username=username, email=email, password=password)
    print('슈퍼유저 생성 완료 ✅')
else:
    print('슈퍼유저 이미 존재합니다.')
