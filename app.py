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

if "forbidden_list" not in st.session_state:
    st.session_state.forbidden_list = DEFAULT_FORBIDDEN.copy()

if "gallery" not in st.session_state:
    st.session_state.gallery = []

st.set_page_config(page_title="스톡 키워드 자동 추출 & 대량 관리", layout="wide")

st.title("🎨 스톡 이미지 대량 키워드 자동 추출 & 관리")
st.caption("미리캔버스(25개) / 크라우드픽(40개) 맞춤 추출 + 금지 키워드 필터링 적용")

# --- Streamlit Secrets에서 API 키 불러오기 ---
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    gemini_api_key = None

# --- 사이드바: 금지 키워드 관리 ---
st.sidebar.header("⚙️ 금지 키워드 관리")
st.sidebar.caption("필터링할 단어를 추가하거나 삭제할 수 있습니다.")

new_forbidden = st.sidebar.text_input("추가할 금지 키워드 입력")
if st.sidebar.button("➕ 금지어 추가"):
    if new_forbidden and new_forbidden.strip() not in st.session_state.forbidden_list:
        st.session_state.forbidden_list.append(new_forbidden.strip())
        st.sidebar.success(f"'{new_forbidden.strip()}' 추가 완료!")
        st.rerun()

with st.sidebar.expander("📋 현재 금지 키워드 목록 관리", expanded=True):
    to_remove = []
    for kw in st.session_state.forbidden_list:
        col1, col2 = st.columns([0.8, 0.2])
        with col1:
            st.write(f"- {kw}")
        with col2:
            if st.button("❌", key=f"del_{kw}", help=f"'{kw}' 삭제"):
                to_remove.append(kw)
                
    if to_remove:
        for kw in to_remove:
            st.session_state.forbidden_list.remove(kw)
        st.rerun()

# --- Gemini 이미지 분석 함수 ---
def analyze_image(image_bytes, api_key, count, forbidden_words):
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
    keyword_list = [k.strip() for k in raw_keywords.replace("\n", "").split(",") if k.strip()]
    filtered_list = [kw for kw in keyword_list if not any(f in kw for f in forbidden_words)]
            
    return ", ".join(filtered_list)

# --- 메인 탭 구성 ---
tab1, tab2 = st.tabs(["📤 대량 이미지 업로드 및 추출", "🖼️ 작업물 보관함 (갤러리)"])

with tab1:
    st.subheader("아이패드 / PC 파일 대량 업로드 (한 번에 15개 이상 가능)")
    
    uploaded_files = st.file_uploader(
        "일러스트/요소 이미지들을 여러 장 선택해 주세요 (PNG, JPG)", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True
    )

    if uploaded_files:
        st.info(f"📁 총 {len(uploaded_files)}개의 파일이 선택되었습니다.")
        
        if st.button("✨ 선택한 이미지 전체 키워드 자동 추출하기", type="primary"):
            if not gemini_api_key:
                st.error("⚠️ Streamlit Secrets에 GEMINI_API_KEY가 설정되어 있지 않습니다.")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                results_container = []
                
                for idx, uploaded_file in enumerate(uploaded_files):
                    status_text.text(f"진행 중 ({idx+1}/{len(uploaded_files)}): {uploaded_file.name} 분석 중...")
                    img_bytes = uploaded_file.getvalue()
                    
                    try:
                        current_forbidden = st.session_state.forbidden_list
                        m_kw = analyze_image(img_bytes, gemini_api_key, 25, current_forbidden)
                        c_kw = analyze_image(img_bytes, gemini_api_key, 40, current_forbidden)
                        
                        results_container.append({
                            "name": uploaded_file.name,
                            "bytes": img_bytes,
                            "miricanvas": m_kw,
                            "crowdpic": c_kw
                        })
                    except Exception as e:
                        st.error(f"'{uploaded_file.name}' 처리 중 오류 발생: {e}")
                        
                    progress_bar.progress((idx + 1) / len(uploaded_files))
                
                status_text.text("✅ 모든 이미지 분석 완료!")
                st.success("아래에서 결과 확인 및 복사, 그리고 보관함 저장을 확인하세요.")
                
                for item in results_container:
                    with st.expander(f"📁 파일명: {item['name']}", expanded=True):
                        col_img, col_txt = st.columns([1, 2])
                        with col_img:
                            st.image(item["bytes"], use_container_width=True)
                        with col_txt:
                            st.markdown("**🎨 미리캔버스용 (25개)**")
                            st.text_area("미리캔버스 복사 영역", value=item["miricanvas"], height=80, key=f"m_{item['name']}")
                            st.markdown("**☁️ 크라우드픽용 (40개)**")
                            st.text_area("크라우드픽 복사 영역", value=item["crowdpic"], height=100, key=f"c_{item['name']}")
                            
                for item in results_container:
                    if not any(g["name"] == item["name"] for g in st.session_state.gallery):
                        st.session_state.gallery.append(item)

with tab2:
    st.subheader("전체 작업물 보관함")
    st.caption("업로드했던 작업물들을 언제든 다시 확인할 수 있습니다.")
    
    if not st.session_state.gallery:
        st.write("아직 업로드된 작업물이 없습니다. 첫 번째 탭에서 이미지를 올려보세요!")
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
