#!/usr/bin/env python3
"""
Supabase 테이블 스키마 테스트 스크립트
실제 cafes 테이블 구조를 확인하고 간단한 INSERT 테스트
"""

import os
import json
from supabase import create_client, Client
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# Supabase 설정
supabase_url = os.environ.get('NEXT_PUBLIC_SUPABASE_URL')
supabase_key = os.environ.get('NEXT_PUBLIC_SUPABASE_ANON_KEY')

def test_table_schema():
    """테이블 스키마 테스트"""
    print("🔍 Supabase 테이블 스키마 테스트")
    print("=" * 50)

    if not supabase_url or not supabase_key:
        print("❌ Supabase 환경 변수가 설정되지 않았습니다.")
        print(f"URL: {supabase_url}")
        print(f"Key: {'***' if supabase_key else 'None'}")
        return

    try:
        # Supabase 클라이언트 생성
        supabase: Client = create_client(supabase_url, supabase_key)
        print("✅ Supabase 연결 성공")

        # 1. 기존 데이터 확인
        print("\n1️⃣ 기존 카페 데이터 확인...")
        response = supabase.table('cafes').select("*").limit(1).execute()

        if response.data:
            sample_cafe = response.data[0]
            print("✅ 기존 데이터 발견:")
            print(f"   컬럼: {list(sample_cafe.keys())}")
            print(f"   샘플: {sample_cafe}")
        else:
            print("ℹ️ 기존 데이터 없음")

        # 2. 최소한의 데이터로 INSERT 테스트
        print("\n2️⃣ 간단한 INSERT 테스트...")

        test_cafe_minimal = {
            "name": "테스트카페_" + str(os.getpid()),
            "address": "서울시 테스트구 테스트동 123",
            "category": "카페"
        }

        try:
            result = supabase.table('cafes').insert(test_cafe_minimal).execute()
            if result.data:
                print("✅ 최소 데이터 INSERT 성공")
                inserted_id = result.data[0]['id']

                # 삽입된 데이터 삭제 (테스트용이므로)
                supabase.table('cafes').delete().eq('id', inserted_id).execute()
                print("🗑️ 테스트 데이터 삭제 완료")
            else:
                print(f"❌ INSERT 실패: {result}")
        except Exception as e:
            print(f"❌ INSERT 테스트 실패: {e}")

        # 3. 점진적으로 필드 추가 테스트
        print("\n3️⃣ 점진적 필드 추가 테스트...")

        test_cases = [
            {
                "name": "테스트카페_위도경도",
                "address": "서울시 테스트구",
                "category": "카페",
                "latitude": 37.5665,
                "longitude": 126.978
            },
            {
                "name": "테스트카페_메뉴",
                "address": "서울시 테스트구",
                "category": "카페",
                "latitude": 37.5665,
                "longitude": 126.978,
                "menu_items": json.dumps({"americano": {"name": "아메리카노", "price": "4000"}})
            }
        ]

        for i, test_case in enumerate(test_cases, 1):
            try:
                result = supabase.table('cafes').insert(test_case).execute()
                if result.data:
                    print(f"✅ 테스트 케이스 {i} 성공: {list(test_case.keys())}")
                    # 즉시 삭제
                    supabase.table('cafes').delete().eq('id', result.data[0]['id']).execute()
                else:
                    print(f"❌ 테스트 케이스 {i} 실패")
            except Exception as e:
                print(f"❌ 테스트 케이스 {i} 오류: {e}")

        print("\n🎯 결론:")
        print("- 위 테스트에서 성공한 필드들이 실제 테이블에 존재하는 컬럼입니다.")
        print("- 실패한 필드들은 테이블에 존재하지 않는 컬럼입니다.")

    except Exception as e:
        print(f"❌ 전체 테스트 실패: {e}")

if __name__ == "__main__":
    test_table_schema()