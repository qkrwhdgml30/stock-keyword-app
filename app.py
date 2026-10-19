import os
import io
import streamlit as st
from PIL import Image
from google import genai
from concurrent.futures import ThreadPoolExecutor

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

st.set_page_config(page_title="스톡 키워드 자동 추출 & 초고속 대량 관리", layout="wide")

st.title("🎨 스톡 이미지 초고속 대량 키워드 추출 & 관리")
st.caption("이미지 자동 압축 및 동시 처리 적용으로 업로드 속도 대폭 단축")

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

# --- 이미지 압축 함수 (속도 향상의 핵심) ---
def optimize_image(image_bytes):
    img = Image.open(io.BytesIO(image_bytes))
    # 이미지가 너무 크면 AI 분석 속도가 느려지므로 긴 축을 800픽셀로 자동 리사이징
    img.thumbnail((800, 800))
    buffer = io.BytesIO()
    # JPEG 형태로 가볍게 변환 압축
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()

# --- Gemini 단건 분석 함수 ---
def analyze_single_image(file_name, image_bytes, api_key, forbidden_words):
    try:
        # 업로드된 이미지를 AI 친화적으로 가볍게 압축
        optimized_bytes = optimize_image(image_bytes)
        
        client = genai.Client(api_key=api_key)
        image = Image.open(io.BytesIO(optimized_bytes))
        
        # 미리캔버스(25개)와 크라우드픽(40개) 키워드를 한 번에 요청하여 횟수 절약 및 속도 단축
        prompt = f"""
        이 이미지의 시각적 요소, 객체, 상황, 인물, 색상, 분위기 등 '요소 본연의 핵심 키워드'만 한국어로 추출해줘.
        1. 첫 번째 줄에는 미리캔버스용 핵심 키워드를 쉼표(,)로 구분하여 정확히 25개 적어줘.
        2. 두 번째 줄에는 크라우드픽용 핵심 키워드를 쉼표(,)로 구분하여 정확히 40개 적어줘.
        다른 설명이나 번호는 절대 붙이지 말고 오직 아래 두 줄 형식으로만 출력해줘:
        미리캔버스: [키워드들...]
        크라우드픽: [키워드들...]

        [절대 포함하지 말아야 할 금지 키워드 리스트]:
        {', '.join(forbidden_words)}
        위 금지 단어들과 유사한 포괄적/제작방식/마케팅성 단어는 반드시 완전히 제외해줘.
        """

        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=[image, prompt]
        )
        
        text_res = response.text.strip()
        m_kw_str, c_kw_str = "", ""
        
        for line in text_res.split("\n"):
            if "미리캔버스:" in line:
                m_kw_str = line.replace("미리캔버스:", "").strip()
            elif "크라우드픽:" in line:
                c_kw_str = line.replace("크라우드픽:", "").strip()
                
        # 파이썬 2차 필터링 검증
        def filter_text(k_str):
            k_list = [k.strip() for k in k_str.replace("\n", "").split(",") if k.strip()]
            filtered = [k for k in k_list if not any(f in k for f in forbidden_words)]
            return ", ".join(filtered)

        return {
            "name": file_name,
            "bytes": image_bytes, # 원본 이미지 보존
            "miricanvas": filter_text(m_kw_str) if m_kw_str else filter_text(text_res),
            "crowdpic": filter_text(c_kw_str) if c_kw_str else filter_text(text_res)
        }
    except Exception as e:
        return {"name": file_name, "error": str(e)}

# --- 메인 탭 구성 ---
tab1, tab2 = st.tabs(["📤 대량 이미지 업로드 및 초고속 추출", "🖼️ 작업물 보관함 (갤러리)"])

with tab1:
    st.subheader("아이패드 / PC 파일 대량 업로드 (한 번에 15개 이상 가능)")
    
    uploaded_files = st.file_uploader(
        "일러스트/요소 이미지들을 여러 장 선택해 주세요 (PNG, JPG)", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True
    )

    if uploaded_files:
        st.info(f"📁 총 {len(uploaded_files)}개의 파일이 선택되었습니다. (동시 처리 최적화 적용)")
        
        if st.button("✨ 초고속 키워드 자동 추출하기", type="primary"):
            if not gemini_api_key:
                st.error("⚠️ Streamlit Secrets에 GEMINI_API_KEY가 설정되어 있지 않습니다.")
            else:
                with st.spinner("🚀 AI가 이미지를 압축하고 동시 분석 중입니다. 잠시만 기다려주세요..."):
                    current_forbidden = st.session_state.forbidden_list
                    
                    results_container = []
                    
                    # ThreadPoolExecutor를 사용해 여러 장을 동시에(병렬로) 처리하여 속도 극대화
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        futures = [
                            executor.submit(analyze_single_image, file.name, file.getvalue(), gemini_api_key, current_forbidden)
                            for file in uploaded_files
                        ]
                        for future in futures:
                            results_container.append(future.result())
                
                st.success("✅ 모든 이미지 분석 완료!")
                
                for item in results_container:
                    if "error" in item:
                        st.error(f"📁 '{item['name']}' 처리 실패: {item['error']}")
                    else:
                        with st.expander(f"📁 파일명: {item['name']}", expanded=True):
                            col_img, col_txt = st.columns([1, 2])
                            with col_img:
                                st.image(item["bytes"], use_container_width=True)
                            with col_txt:
                                st.markdown("**🎨 미리캔버스용 (25개)**")
                                st.text_area("미리캔버스 복사 영역", value=item["miricanvas"], height=80, key=f"m_{item['name']}")
                                st.markdown("**☁️ 크라우드픽용 (40개)**")
                                st.text_area("크라우드픽 복사 영역", value=item["crowdpic"], height=100, key=f"c_{item['name']}")
                                
                # 세션 갤러리에 누적 저장
                for item in results_container:
                    if "error" not in item:
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
