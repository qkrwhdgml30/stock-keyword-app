import os
import io
import streamlit as st
from PIL import Image
from google import genai
from google.genai import types

# --- 설정 및 금지 키워드 목록 정의 ---
FORBIDDEN_KEYWORDS = [
    # 뭉뚱그려진 포괄적 키워드
    "감성일러스트", "다이어리요소", "디자인소스", "그래픽소스", "그래픽요소", 
    "포인트일러스트", "ppt요소", "카드뉴스요소", "아이콘", "라인아이콘", "디자인재료",
    # 속성 / 마케팅 / 제작 방식 키워드
    "벡터", "누끼", "투명배경", "마켓팅용아님", "감성적인표현제외"
]

# 이미지 세션(보관함) 초기화
if "gallery" not in st.session_state:
    st.session_state.gallery = []

st.set_page_config(page_title="스톡 키워드 자동 추출기 (무료버전)", layout="wide")

st.title("🎨 스톡 이미지 키워드 자동 추출 & 관리 (무료)")
st.caption("미리캔버스 / 크라우드픽 심사 거절 방지 (Gemini 무료 API 적용)")

# 사이드바: API 키 입력
api_key_input = st.sidebar.text_input("Google Gemini API Key 입력", type="password")

# --- Gemini 이미지 분석 함수 ---
def analyze_image_and_extract_keywords(image_bytes, api_key):
    client = genai.Client(api_key=api_key)
    image = Image.open(io.BytesIO(image_bytes))
    
    prompt = f"""
    이 이미지의 시각적 요소, 객체, 상황, 인물, 색상, 분위기 등 '요소 본연의 핵심 키워드'만 한국어로 20~30개 추출해줘.
    결과는 쉼표(,)로 구분된 단어 리스트로 제공해줘.

    [절대 포함하지 말아야 할 금지 키워드 리스트]:
    {', '.join(FORBIDDEN_KEYWORDS)}
    위 금지 단어들과 유사한 포괄적/제작방식/마케팅성 단어는 반드시 완전히 제외하고 오직 그림 속 객체와 상황 자체만 키워드로 뽑아줘.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[image, prompt]
    )
    
    raw_keywords = response.text.strip()
    
    # Python 단에서 한번 더 금지어 2차 강력 검증 및 필터링
    keyword_list = [k.strip() for k in raw_keywords.replace("\n", "").split(",") if k.strip()]
    filtered_list = []
    for kw in keyword_list:
        if not any(forbidden in kw for forbidden in FORBIDDEN_KEYWORDS):
            filtered_list.append(kw)
            
    return ", ".join(filtered_list)

# --- 메인 탭 구성 ---
tab1, tab2 = st.tabs(["📤 이미지 업로드 및 키워드 추출", "🖼️ 작업물 보관함 (갤러리)"])

with tab1:
    st.subheader("아이패드 / PC 파일 직접 업로드")
    uploaded_file = st.file_uploader("일러스트/요소 이미지를 올려주세요 (PNG, JPG)", type=["png", "jpg", "jpeg"])

    if uploaded_file is not None:
        st.image(uploaded_file, caption="업로드된 이미지", width=300)
        
        if st.button("✨ 키워드 자동 추출하기", type="primary"):
            if not api_key_input:
                st.error("좌측 사이드바에 Google Gemini API Key를 입력해주세요!")
            else:
                with st.spinner("Gemini AI가 금지 키워드를 걸러내고 키워드를 추출 중입니다..."):
                    img_bytes = uploaded_file.getvalue()
                    try:
                        result_keywords = analyze_image_and_extract_keywords(img_bytes, api_key_input)
                        
                        st.success("키워드 추출 완료!")
                        st.text_area("🔑 최종 정제된 키워드 (복사해서 사용하세요)", value=result_keywords, height=120)
                        
                        # 갤러리에 자동 저장
                        st.session_state.gallery.append({
                            "name": uploaded_file.name,
                            "bytes": img_bytes,
                            "keywords": result_keywords
                        })
                        st.info("💡 '작업물 보관함' 탭에 이 작업물이 자동 저장되었습니다.")
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")

with tab2:
    st.subheader("올렸던 이미지 및 키워드 다시보기")
    if not st.session_state.gallery:
        st.write("아직 저장된 이미지 작업물이 없습니다.")
    else:
        # 3열 갤러리 레이아웃
        cols = st.columns(3)
        for idx, item in enumerate(st.session_state.gallery):
            col = cols[idx % 3]
            with col:
                st.image(item["bytes"], use_container_width=True)
                st.caption(f"📁 {item['name']}")
                
                # 이미지 클릭 시 키워드 확인용 버튼/팝업
                with st.expander("🔍 키워드 보기"):
                    st.code(item["keywords"], language="text")
