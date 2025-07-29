# Railway에서 Selenium 실행을 위한 Dockerfile
FROM python:3.11-slim

# 시스템 패키지 업데이트 및 Chrome 설치를 위한 의존성 설치
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Chrome 설치
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriver 명시적 설치 (명령어 문법 오류 수정)
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && \
    ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        CHROME_VERSION=$(google-chrome --version | cut -d ' ' -f 3 | cut -d '.' -f 1-3) && \
        DRIVER_URL=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json" | grep -o '"url": "[^"]*chromedriver-linux64[^"]*"' | grep "$CHROME_VERSION" | sed 's/"url": "\([^"]*\)"/\1/' | head -n 1) && \
        wget -q "$DRIVER_URL" -O /tmp/chromedriver.zip && \
        unzip /tmp/chromedriver.zip -d /tmp/ && \
        mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
        chmod +x /usr/local/bin/chromedriver && \
        rm /tmp/chromedriver.zip && rm -rf /tmp/chromedriver-linux64; \
    else \
        echo "Unsupported architecture: $ARCH"; \
        exit 1; \
    fi && \
    apt-get purge -y --auto-remove curl unzip

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

# 포트 노출 (Railway 기본 포트인 5000으로 설정)
EXPOSE 5000

# 애플리케이션 실행 (Railway에서 제공하는 PORT 환경 변수 사용)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --timeout 300 --workers 1 app:app"]
