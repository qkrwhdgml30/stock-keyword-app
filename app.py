import os
import io
import streamlit as st
from PIL import Image
from google import genai

# --- 기본 금지 키워드 초기값 설정 ---
DEFAULT_FORBIDDEN = [
    "감성일러스트", "다이어리요소", "디자인소스", "그래픽소스", "그래픽요소", 
    "포인트일러스트", "ppt요소", "카드뉴스요소", "아이콘", "라인아이콘", "디자인재료",
    "벡터", "누끼", "투명배경", "마켓팅용아님", "감성적인표현제외"
]

# 세션에 금지 키워드 리스트 저장 (웹 화면에서 수정 가능하도록)
if "forbidden_list" not in st.session_state:
    st.session_state.forbidden_list = DEFAULT_FORBIDDEN.copy()

# 이미지 세션(보관함) 초기화
if "gallery" not in st.session_state:
    st.session_state.gallery = []

st.set_page_config(page_title="스톡 키워드 자동 추출기", layout="wide")

st.title("🎨 스톡 이미지 키워드 자동 추출 & 관리")
st.caption("미리캔버스(25개) / 크라우드픽(40개) 플랫폼별 맞춤 키워드 자동 분리 (금지 키워드 실시간 편집 가능)")

# --- 사이드바 구성 ---
st.sidebar.header("⚙️ 설정 & 금지 키워드 관리")

# 1. API 키 입력
api_key_input = st.sidebar.text_input("Google Gemini API Key 입력", type="password")

st.sidebar.markdown("---")

# 2. 금지 키워드 추가/삭제 기능
st.sidebar.subheader("🚫 금지 키워드 편집")
st.sidebar.caption("필터링할 단어를 추가하거나 삭제할 수 있습니다.")

# 새로운 금지어 추가 입력란
new_forbidden = st.sidebar.text_input("추가할 금지 키워드 입력")
if st.sidebar.button("➕ 금지어 추가"):
    if new_forbidden and new_forbidden.strip() not in st.session_state.forbidden_list:
        st.session_state.forbidden_list.append(new_forbidden.strip())
        st.sidebar.success(f"'{new_forbidden.strip()}' 추가 완료!")
        st.rerun()

# 현재 등록된 금지어 목록 보기 및 개별 삭제
with st.sidebar.expander("📋 현재 금지 키워드 목록 관리", expanded=True):
    # 삭제할 항목을 체크하기 위해 멀티셀렉트 또는 버튼 활용
    to_remove = []
    for kw in st.session_state.forbidden_list:
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            st.write(f"- {kw}")
        with col2:
            if st.button("❌", key=f"del_{kw}", help=f"'{kw}' 삭제"):
                to_remove.append(kw)
                
    # 삭제 처리
    if to_remove:
        for kw in to_remove:
            st.session_state.forbidden_list.remove(kw)
        st.rerun()

# --- Gemini 이미지 분석 및 플랫폼별 개수 조절 함수 ---
def analyze_image_and_extract_keywords(image_bytes, api_key, count, forbidden_words):
    client = genai.Client(api_key=api_key)
    image = Image.open(io.BytesIO(image_bytes))
    
    prompt = f"""
    이 이미지의 시각적 요소, 객체, 상황, 인물, 색상, 분위기 등 '요소 본연의 핵심 키워드'만 한국어로 정확히 {count}개 추출해줘.
    결과는 쉼표(,)로 구분된 단어 리스트로 제공해줘. 다른 설명이나 번호는 절대 붙이지 마.

    [절대 포함하지 말아야 할 금지 키워드 리스트]:
    {', '.join(forbidden_words)}
    위 금지 단어들과 유사한 포괄적/제작방식/마케팅성 단어는 반드시 완전히 제외하고 오직 그림 속 객체와 상황 자체만 키워드로 뽑아줘.
    """

    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=[image, prompt]
    )
    
    raw_keywords = response.text.strip()
    
    # Python 단에서 한번 더 금지어 2차 강력 검증 및 필터링
    keyword_list = [k.strip() for k in raw_keywords.replace("\n", "").split(",") if k.strip()]
    filtered_list = []
    for kw in keyword_list:
        if not any(forbidden in kw for forbidden in forbidden_words):
            filtered_list.append(kw)
            
    return ", ".join(filtered_list)

# --- 메인 탭 구성 ---
tab1, tab2 = st.tabs(["📤 이미지 업로드 및 키워드 추출", "🖼️ 작업물 보관함 (갤러리)"])

with tab1:
    st.subheader("아이패드 / PC 파일 직접 업로드")
    uploaded_file = st.file_uploader("일러스트/요소 이미지를 올려주세요 (PNG, JPG)", type=["png", "jpg", "jpeg"])

    if uploaded_file is not None:
        st.image(uploaded_file, caption="업로드된 이미지", width=300)
        
        if st.button("✨ 플랫폼별 키워드 자동 추출하기", type="primary"):
            if not api_key_input:
                st.error("좌측 사이드바에 Google Gemini API Key를 입력해주세요!")
            else:
                with st.spinner("AI가 금지 키워드를 반영하여 키워드를 추출 중입니다..."):
                    img_bytes = uploaded_file.getvalue()
                    try:
                        # 현재 적용된 금지 키워드 리스트 전달
                        current_forbidden = st.session_state.forbidden_list
                        
                        miricanvas_keywords = analyze_image_and_extract_keywords(img_bytes, api_key_input, 25, current_forbidden)
                        crowdpic_keywords = analyze_image_and_extract_keywords(img_bytes, api_key_input, 40, current_forbidden)
                        
                        st.success("키워드 추출 완료!")
                        
                        st.markdown("### 🎨 미리캔버스용 키워드 (최대 25개)")
                        st.text_area("미리캔버스 복사 영역", value=miricanvas_keywords, height=100, key="m_area")
                        
                        st.markdown("### ☁️ 크라우드픽용 키워드 (최대 40개)")
                        st.text_area("크라우드픽 복사 영역", value=crowdpic_keywords, height=130, key="c_area")
                        
                        # 갤러리에 자동 저장
                        st.session_state.gallery.append({
                            "name": uploaded_file.name,
                            "bytes": img_bytes,
                            "miricanvas": miricanvas_keywords,
                            "crowdpic": crowdpic_keywords
                        })
                        st.info("💡 '작업물 보관함' 탭에 이 작업물이 자동 저장되었습니다.")
                    except Exception as e:
                        st.error(f"오류가 발생했습니다: {e}")

with tab2:
    st.subheader("올렸던 이미지 및 플랫폼별 키워드 다시보기")
    if not st.session_state.gallery:
        st.write("아직 저장된 이미지 작업물이 없습니다.")
    else:
        cols = st.columns(3)
        for idx, item in enumerate(st.session_state.gallery):
            col = cols[idx % 3]
            with col:
                st.image(item["bytes"], use_container_width=True)
                st.caption(f"📁 {item['name']}")
                
                with st.expander("🔍 키워드 보기"):
                    st.markdown("**[미리캔버스용]**")
                    st.code(item["miricanvas"], language="text")
                    st.markdown("**[크라우드픽용]**")
                    st.code(item["crowdpic"], language="text")
