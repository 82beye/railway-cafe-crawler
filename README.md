# Cafe Crawler for Railway

네이버 지도에서 카페 정보를 크롤링하여 Supabase에 저장하는 Python 스크립트입니다.

## 기능

- 네이버 지도에서 카페 정보 크롤링
- 메뉴 정보 포함한 상세 데이터 수집
- Supabase 데이터베이스에 자동 저장
- Railway 플랫폼에서 실행 가능

## Railway 배포 방법

### 1. 환경 변수 설정

Railway 대시보드에서 다음 환경 변수를 설정하세요:

```
NEXT_PUBLIC_KAKAO_REST_API_KEY=your_kakao_api_key
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
```

### 2. 배포

1. 이 레포지토리를 GitHub에 push
2. Railway에서 GitHub 레포지토리 연결
3. 자동으로 배포됩니다

### 3. 실행

배포 후 Railway에서 제공하는 URL로 GET 요청을 보내면 크롤링이 시작됩니다:

```
GET https://your-railway-app.railway.app/crawl?lat=37.5665&lng=126.9780
```

## 로컬 실행

```bash
pip install -r requirements.txt
python app.py
```

## 문제 해결

### ChromeDriver 오류 (WinError 193, Exec format error)

이 오류는 Railway 환경에서 ChromeDriver 실행 파일이 올바르게 설치되지 않았을 때 발생합니다.

**해결 방법:**
1. Dockerfile이 Chrome과 ChromeDriver를 올바르게 설치하도록 수정됨
2. 환경 변수로 Chrome 바이너리와 ChromeDriver 경로 설정
3. Railway 환경에 최적화된 Chrome 옵션 적용

### 메모리 부족 오류

- Chrome 옵션에서 메모리 사용량 최적화
- `--single-process`, `--disable-dev-shm-usage` 등의 옵션 적용
- Railway Pro 플랜 사용 권장

### 타임아웃 오류

- gunicorn 타임아웃을 300초로 설정
- 크롤링 작업이 완료될 때까지 충분한 시간 제공

## 주의사항

- Selenium을 사용하므로 메모리 사용량이 높습니다
- Railway의 무료 티어 제한을 고려하여 사용하세요
- 크롤링 대상 사이트의 이용약관을 준수하세요