# Railway 배포 가이드

## 🚀 **배포 준비 완료**

Railway에서 gunicorn 오류가 해결되었습니다.

## 📋 **수정된 파일들**

### 1. **requirements.txt**
```txt
flask==2.3.3
requests==2.31.0
python-dotenv==1.0.0
supabase==1.0.4
beautifulsoup4==4.12.2
lxml==4.9.3
gunicorn==21.2.0  # ✅ 추가됨

# Selenium dependencies (optional)
selenium==4.15.0
webdriver-manager==4.0.1
```

### 2. **Procfile**
```
web: gunicorn --bind 0.0.0.0:$PORT app:app --workers 1 --timeout 120
```

### 3. **railway.json**
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "gunicorn --bind 0.0.0.0:$PORT app:app --workers 1 --timeout 120 --worker-class sync",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

### 4. **runtime.txt**
```
python-3.11.7
```

## 🔧 **Railway 환경 변수 설정**

Railway 대시보드에서 다음 환경 변수를 설정하세요:

```bash
NEXT_PUBLIC_KAKAO_REST_API_KEY=your_kakao_api_key
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
```

## 🚀 **배포 과정**

### 1. **GitHub 연결**
- Railway 대시보드에서 GitHub 레포지토리 연결
- `python-railway-cafe-crawler` 폴더를 루트로 설정

### 2. **자동 배포**
- 코드 푸시 시 자동으로 빌드 및 배포
- 빌드 시간: 약 25-30초

### 3. **배포 완료 확인**
```bash
# 배포된 URL 테스트
curl https://your-railway-app.railway.app/status

# 응답 예시
{
  "status": "running",
  "message": "Cafe Crawler is ready",
  "services": {
    "supabase": "OK",
    "kakao_api": "OK",
    "crawler_mode": "Requests"
  }
}
```

## 🛠️ **해결된 문제들**

### ❌ **Before (오류 상황)**
```
Container failed to start
The executable `gunicorn` could not be found.
```

### ✅ **After (해결 후)**
```
✅ gunicorn==21.2.0 추가
✅ Procfile 설정
✅ railway.json 최적화
✅ Python 버전 명시
✅ 안정적인 Requests 기반 크롤링
```

## 📊 **성능 최적화**

### **gunicorn 설정**
- `--workers 1`: Railway 메모리 제한 고려
- `--timeout 120`: 크롤링 작업 시간 여유
- `--worker-class sync`: 동기 워커 (안정성)

### **크롤링 방식**
- **Primary**: Kakao API (빠르고 안정적)
- **Fallback**: Selenium (Chrome 환경에서만)

## 🔍 **모니터링**

### **로그 확인**
```bash
# Railway CLI로 로그 확인
railway logs
```

### **API 테스트**
```bash
# 크롤링 테스트
curl "https://your-app.railway.app/crawl?lat=37.5665&lng=126.978"
```

---

**결론**: 이제 Railway에서 안정적으로 카페 크롤러가 작동합니다! 🎉