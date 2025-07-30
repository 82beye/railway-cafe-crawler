# Railway에서 Selenium 실행을 위한 Dockerfile
FROM python:3.11-slim

# 시스템 패키지 업데이트 및 Chrome 설치를 위한 의존성 설치
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    unzip \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Chrome 설치
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriver는 webdriver-manager를 통해 런타임에 자동 설치됨
# 이 방식이 Chrome 버전 호환성 문제를 자동으로 해결함

# 작업 디렉토리 설정
WORKDIR /app

# Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 환경 변수 설정
ENV PYTHONUNBUFFERED=1
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV DISPLAY=:99
ENV DEBIAN_FRONTEND=noninteractive

# 포트 노출 (Railway에서 동적 할당)
EXPOSE 5000

# 애플리케이션 실행 (Railway의 5000 PORT 사용)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:5000 --timeout 300 --workers 1 app:app"]
