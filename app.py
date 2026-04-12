import streamlit as st
import os
import json
import base64
import time
from datetime import datetime
from streamlit_js_eval import streamlit_js_eval as _st_js_eval
from config import MODE_CONFIG, COMMON_SETTINGS, QUALITY_CHECKLIST, IMAGE_PROMPTS
from ai_clients import fetch_page_content, search_competitors
from pipeline import PipelineState, execute_step, execute_image_generation
from utils import (
    parse_keyword_csv, parse_ga4_data, parse_ad_data,
    extract_text_from_pdf, extract_newsletter_analysis,
    generate_markdown_report, generate_session_json,
    create_learning_data, load_learning_data,
    create_before_after_table, summarize_page_data
)


# ============================================================================
# ページ設定
# ============================================================================

st.set_page_config(
    page_title="AI Marketing Studio",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================================================
# パスワード認証
# ============================================================================

def check_password() -> bool:
    """パスワード認証を確認"""
    correct_password = None
    try:
        correct_password = st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        correct_password = os.environ.get("APP_PASSWORD")

    if not correct_password:
        st.warning("⚠️ パスワードが設定されていません")
        return True

    if not st.session_state.get("authenticated", False):
        st.title("🔐 AI Marketing Studio")
        st.caption("マーケティングAIパイプライン")
        password = st.text_input("パスワード", type="password")
        if st.button("ログイン", type="primary"):
            if password == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ パスワードが正しくありません")
        st.stop()

    return True


# ============================================================================
# セッション状態の初期化
# ============================================================================

def init_session_state() -> None:
    """セッション状態を初期化"""
    defaults = {
        "authenticated": False,
        "current_mode": None,
        "pipeline_state": None,
        "session_history": [],
        "form_data": {},
        "uploaded_data": {},
        "competitor_data": {},
        "learning_data": None,
        "user_edits": [],
        "cross_mode_results": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================================
# サイドバー - APIキー設定
# ============================================================================

def render_api_keys_section() -> dict:
    """APIキー設定セクション（ブラウザlocalStorageへの保存対応）"""
    st.sidebar.markdown("### 🔑 APIキー設定")

    api_keys = {}

    # Secrets / 環境変数から取得を試みる
    def _get_secret(name: str) -> str:
        try:
            return st.secrets[name]
        except (KeyError, FileNotFoundError):
            return os.environ.get(name, "")

    _sk_anthropic = _get_secret("ANTHROPIC_API_KEY")
    _sk_openai    = _get_secret("OPENAI_API_KEY")
    _sk_gemini    = _get_secret("GEMINI_API_KEY")
    secrets_ok = bool(_sk_anthropic and _sk_openai and _sk_gemini)

    # ブラウザ保存キーの初期化
    if "ms_bk" not in st.session_state:
        st.session_state.ms_bk = {"a": "", "o": "", "g": ""}
        st.session_state.ms_bk_loaded = False

    # localStorageから読み込み（初回のみ）
    if not secrets_ok and not st.session_state.ms_bk_loaded:
        _js_val = _st_js_eval(
            js_expressions='JSON.stringify({a:localStorage.getItem("aims_a")||"",o:localStorage.getItem("aims_o")||"",g:localStorage.getItem("aims_g")||""})',
            key="ms_bk_load"
        )
        if _js_val is not None:
            try:
                st.session_state.ms_bk = json.loads(_js_val)
            except (json.JSONDecodeError, TypeError):
                pass
            st.session_state.ms_bk_loaded = True
            _bk = st.session_state.ms_bk
            if _bk.get("a") and _bk.get("o") and _bk.get("g"):
                st.rerun()

    bk = st.session_state.ms_bk
    browser_ok = bool(bk.get("a") and bk.get("o") and bk.get("g"))

    if secrets_ok:
        # Secrets設定済み
        st.sidebar.success("🔑 APIキー: Secrets設定済み")
        api_keys["anthropic"] = _sk_anthropic
        api_keys["openai"]    = _sk_openai
        api_keys["gemini"]    = _sk_gemini

    elif browser_ok:
        # localStorage保存済み
        st.sidebar.success("🔑 APIキー: 保存済み ✅")
        api_keys["anthropic"] = bk["a"]
        api_keys["openai"]    = bk["o"]
        api_keys["gemini"]    = bk["g"]
        with st.sidebar.expander("🔧 キー管理", expanded=False):
            if st.button("🗑️ 保存したキーを削除", use_container_width=True, key="del_ms_keys"):
                _st_js_eval(
                    js_expressions='localStorage.removeItem("aims_a");localStorage.removeItem("aims_o");localStorage.removeItem("aims_g");"ok"',
                    key="ms_del_keys"
                )
                st.session_state.ms_bk = {"a": "", "o": "", "g": ""}
                st.session_state.ms_bk_loaded = True
                st.rerun()

    else:
        # 手動入力
        api_keys["anthropic"] = st.sidebar.text_input(
            "Anthropic API Key", type="password", key="anthropic_key",
            placeholder="sk-ant-..."
        )
        api_keys["openai"] = st.sidebar.text_input(
            "OpenAI API Key", type="password", key="openai_key",
            placeholder="sk-..."
        )
        api_keys["gemini"] = st.sidebar.text_input(
            "Google Gemini API Key", type="password", key="gemini_key",
            placeholder="AI..."
        )

        # 3つ揃ったら保存ボタンを表示
        if api_keys["anthropic"] and api_keys["openai"] and api_keys["gemini"]:
            if st.sidebar.button("💾 ブラウザに保存", type="primary", use_container_width=True, key="save_ms_keys"):
                _save_js = (
                    f'localStorage.setItem("aims_a",{json.dumps(api_keys["anthropic"])});'
                    f'localStorage.setItem("aims_o",{json.dumps(api_keys["openai"])});'
                    f'localStorage.setItem("aims_g",{json.dumps(api_keys["gemini"])});"ok"'
                )
                _st_js_eval(js_expressions=_save_js, key="ms_save_keys")
                st.session_state.ms_bk = {
                    "a": api_keys["anthropic"],
                    "o": api_keys["openai"],
                    "g": api_keys["gemini"]
                }
                st.session_state.ms_bk_loaded = True
                st.sidebar.success("✅ 保存完了！次回から自動読み込みされます")
                time.sleep(1)
                st.rerun()
            st.sidebar.caption("💡 このブラウザにのみ保存されます")

    api_keys.setdefault("anthropic", "")
    api_keys.setdefault("openai", "")
    api_keys.setdefault("gemini", "")

    st.sidebar.divider()

    with st.sidebar.expander("🔍 検索API（オプション）"):
        api_keys["google_search"] = st.text_input(
            "Google Custom Search API Key", type="password", key="google_search_key"
        )
        api_keys["google_search_engine_id"] = st.text_input(
            "Google Search Engine ID", type="password", key="search_engine_id_key"
        )

    # ステータス表示
    st.sidebar.markdown("**APIステータス**")
    status_cols = st.sidebar.columns(3)
    status_cols[0].markdown(f"{'✅' if api_keys['anthropic'] else '❌'} Anthropic")
    status_cols[1].markdown(f"{'✅' if api_keys['openai'] else '❌'} OpenAI")
    status_cols[2].markdown(f"{'✅' if api_keys['gemini'] else '❌'} Gemini")

    return api_keys


# ============================================================================
# サイドバー - 学習データセクション
# ============================================================================

def render_learning_data_section() -> None:
    """学習データセクション"""
    st.sidebar.markdown("### 📚 学習データ")

    learning_file = st.sidebar.file_uploader(
        "前回の学習データを読み込む (.json)",
        type="json",
        key="learning_data_upload"
    )

    if learning_file is not None:
        learning_data = json.load(learning_file)
        st.session_state.learning_data = learning_data
        if "client_name" in learning_data:
            st.sidebar.success(f"✅ {learning_data.get('client_name')} の学習データを読み込みました")


# ============================================================================
# サイドバー - セッション履歴セクション
# ============================================================================

def render_session_history_section() -> None:
    """セッション履歴セクション"""
    if st.session_state.session_history:
        st.sidebar.markdown("### 📜 セッション履歴")

        for idx, session in enumerate(st.session_state.session_history):
            with st.sidebar.expander(
                f"🕐 {session.get('timestamp', '').split('T')[0]} - {session.get('mode', 'Unknown')}"
            ):
                st.write(f"クライアント: {session.get('client_name', 'N/A')}")
                st.write(f"モード: {session.get('mode', 'N/A')}")
                if "summary" in session:
                    st.write(session["summary"])


# ============================================================================
# サイドバー - モード間連携セクション
# ============================================================================

def render_cross_mode_section() -> None:
    """モード間連携セクション"""
    if st.session_state.cross_mode_results:
        st.sidebar.markdown("### 🔗 モード間連携")
        use_cross_mode = st.sidebar.checkbox("他モードの結果を参照")

        if use_cross_mode:
            st.sidebar.markdown("**利用可能な結果:**")
            for mode, data in st.session_state.cross_mode_results.items():
                st.sidebar.write(f"- {mode}")


# ============================================================================
# サイドバー統合
# ============================================================================

def render_sidebar() -> dict:
    """サイドバー全体をレンダー"""
    api_keys = render_api_keys_section()
    render_learning_data_section()
    render_session_history_section()
    render_cross_mode_section()

    return api_keys


# ============================================================================
# モード選択画面
# ============================================================================

def render_mode_selection() -> None:
    """モード選択画面"""
    st.markdown("# 🎯 AI Marketing Studio v1.0.0")
    st.markdown("マーケティング戦略の立案から実装まで、AIが一気通貫でサポート")
    st.divider()

    modes = [
        {
            "key": "seo",
            "icon": "🔍",
            "name": "SEO最適化",
            "description": "既存ページの改善または新規ページ作成のためのSEO戦略"
        },
        {
            "key": "email",
            "icon": "📧",
            "name": "メールマーケティング",
            "description": "メルマガシーケンスの作成・改善でリード育成"
        },
        {
            "key": "ads",
            "icon": "📢",
            "name": "広告運用最適化",
            "description": "Google Ads、Facebookなど複数プラットフォームの広告改善"
        },
        {
            "key": "lp",
            "icon": "📄",
            "name": "ランディングページ",
            "description": "高い転換率を実現するLP制作・改善"
        },
        {
            "key": "cro",
            "icon": "📊",
            "name": "CRO分析",
            "description": "既存サイトの総合的なコンバージョン最適化"
        },
    ]

    cols = st.columns(2)
    for idx, mode in enumerate(modes):
        col_idx = idx % 2
        with cols[col_idx]:
            with st.container(border=True):
                st.markdown(f"### {mode['icon']} {mode['name']}")
                st.markdown(mode['description'])
                if st.button(
                    "このモードで開始 →",
                    key=f"mode_btn_{mode['key']}",
                    use_container_width=True
                ):
                    st.session_state.current_mode = mode['key']
                    st.session_state.form_data = {}
                    st.session_state.uploaded_data = {}
                    st.rerun()


# ============================================================================
# 共通フォーム - 基本情報
# ============================================================================

def render_basic_info_form() -> None:
    """基本情報フォーム"""
    st.markdown("### 📋 基本情報")

    st.session_state.form_data["client_name"] = st.text_input(
        "クライアント名（任意）",
        value=st.session_state.form_data.get("client_name", ""),
        key="client_name_input"
    )

    st.session_state.form_data["industry"] = st.text_input(
        "業界/業種",
        value=st.session_state.form_data.get("industry", ""),
        key="industry_input"
    )


# ============================================================================
# 共通フォーム - ペルソナ設定
# ============================================================================

def render_persona_form() -> None:
    """ペルソナ設定フォーム"""
    st.markdown("### 👥 ターゲットペルソナ")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.session_state.form_data["persona_age"] = st.selectbox(
            "年齢層",
            ["", "10代", "20代", "30代", "40代", "50代", "60代以上"],
            index=0,
            key="persona_age_select"
        )

    with col2:
        st.session_state.form_data["persona_gender"] = st.selectbox(
            "性別",
            ["", "男性", "女性", "その他"],
            index=0,
            key="persona_gender_select"
        )

    with col3:
        st.session_state.form_data["persona_job"] = st.text_input(
            "職業",
            value=st.session_state.form_data.get("persona_job", ""),
            key="persona_job_input"
        )

    st.session_state.form_data["persona_pain"] = st.text_area(
        "ペルソナの課題・悩み",
        value=st.session_state.form_data.get("persona_pain", ""),
        height=80,
        key="persona_pain_input"
    )


# ============================================================================
# 共通フォーム - USP・競合・目的
# ============================================================================

def render_usp_competition_form() -> None:
    """USP・競合・目的フォーム"""
    st.markdown("### 🎯 USP・競合分析・目的設定")

    st.session_state.form_data["usp"] = st.text_area(
        "USP/強み（独自の価値提案）",
        value=st.session_state.form_data.get("usp", ""),
        height=80,
        key="usp_input"
    )

    st.session_state.form_data["competitors"] = st.text_area(
        "主な競合企業・製品",
        value=st.session_state.form_data.get("competitors", ""),
        height=80,
        key="competitors_input"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.session_state.form_data["goal"] = st.selectbox(
            "主な目的",
            ["", "CV獲得", "認知向上", "リテンション", "リード獲得"],
            index=0,
            key="goal_select"
        )

    with col2:
        st.session_state.form_data["tone"] = st.selectbox(
            "トーン",
            ["", "フォーマル", "カジュアル", "専門的", "親しみやすい"],
            index=0,
            key="tone_select"
        )


# ============================================================================
# 共通フォーム - 画像生成オプション
# ============================================================================

def render_image_generation_form() -> None:
    """画像生成オプションフォーム"""
    st.markdown("### 🖼️ 画像生成オプション")

    st.session_state.form_data["image_quality"] = st.selectbox(
        "画像生成品質",
        ["OFF", "Medium品質", "High品質"],
        index=0,
        key="image_quality_select"
    )


# ============================================================================
# SEOモード固有フォーム
# ============================================================================

def render_seo_mode_form() -> None:
    """SEOモード固有フォーム"""
    st.markdown("### 🔍 SEO最適化設定")

    seo_submode = st.radio(
        "SEO分析タイプ",
        ["既存ページ改善", "新規ページ作成"],
        key="seo_submode_radio"
    )
    st.session_state.form_data["seo_submode"] = seo_submode

    if seo_submode == "既存ページ改善":
        st.session_state.form_data["target_url"] = st.text_input(
            "対象ページのURL",
            value=st.session_state.form_data.get("target_url", ""),
            key="target_url_input"
        )

        st.markdown("スクリーンショット（任意）")
        screenshot_file = st.file_uploader(
            "ページのスクリーンショット",
            type=["png", "jpg", "jpeg"],
            key="seo_screenshot_upload"
        )
        if screenshot_file:
            st.session_state.uploaded_data["page_screenshot"] = screenshot_file.getvalue()

    else:
        st.session_state.form_data["target_keywords"] = st.text_input(
            "ターゲットキーワード",
            value=st.session_state.form_data.get("target_keywords", ""),
            key="target_keywords_input"
        )

    st.markdown("**キーワード・データアップロード（任意）**")

    keyword_file = st.file_uploader(
        "キーワードCSV（Ahrefs等）",
        type="csv",
        key="keyword_csv_upload"
    )
    if keyword_file:
        keywords = parse_keyword_csv(keyword_file)
        st.session_state.uploaded_data["keywords"] = keywords
        st.success(f"✅ {len(keywords)}件のキーワードを読み込みました")

    ga4_file = st.file_uploader(
        "GA4データCSV（任意）",
        type="csv",
        key="ga4_csv_upload"
    )
    if ga4_file:
        ga4_data = parse_ga4_data(ga4_file)
        st.session_state.uploaded_data["ga4_data"] = ga4_data
        st.success("✅ GA4データを読み込みました")

    st.markdown("**競合リサーチ方法**")
    research_method = st.radio(
        "競合調査方法",
        ["URLを入力", "キーワードから自動検索"],
        key="research_method_radio"
    )

    if research_method == "URLを入力":
        st.session_state.form_data["competitor_urls"] = st.text_area(
            "競合URLを1行1つぞつ入力",
            value=st.session_state.form_data.get("competitor_urls", ""),
            height=100,
            key="competitor_urls_input"
        )
    else:
        st.session_state.form_data["competitor_search_keyword"] = st.text_input(
            "検索キーワード（Google Custom Search APIが必要）",
            value=st.session_state.form_data.get("competitor_search_keyword", ""),
            key="competitor_search_keyword_input"
        )


# ============================================================================
# メールモード固有フォーム
# ============================================================================

def render_email_mode_form() -> None:
    """メールモード固有フォーム"""
    st.markdown("### 📧 メールマーケティング設定")

    st.session_state.form_data["sequence_count"] = st.number_input(
        "配信回数/シーケンス数",
        min_value=1,
        max_value=20,
        value=st.session_state.form_data.get("sequence_count", 5),
        key="sequence_count_input"
    )

    st.markdown("**既存メルマガ分析（任意）**")
    existing_newsletter = st.file_uploader(
        "既存メルマガ（PDF/TXT）",
        type=["pdf", "txt"],
        key="existing_newsletter_upload"
    )
    if existing_newsletter:
        if existing_newsletter.type == "application/pdf":
            newsletter_text = extract_text_from_pdf(existing_newsletter)
        else:
            newsletter_text = existing_newsletter.read().decode("utf-8")

        analysis = extract_newsletter_analysis(newsletter_text)
        st.session_state.uploaded_data["newsletter_analysis"] = analysis
        st.success("✅ メルマガを分析しました")

    st.markdown("**テストデータ（任意）**")
    test_newsletter = st.file_uploader(
        "メルマガテスト（ビフォーアフター比較用）",
        type=["pdf", "txt"],
        key="test_newsletter_upload"
    )
    if test_newsletter:
        if test_newsletter.type == "application/pdf":
            test_text = extract_text_from_pdf(test_newsletter)
        else:
            test_text = test_newsletter.read().decode("utf-8")
        st.session_state.uploaded_data["test_newsletter"] = test_text

    st.session_state.form_data["email_proposal_type"] = st.selectbox(
        "提案タイプ",
        ["", "ゼロベース提案", "トレンドベース提案", "既存改善"],
        index=0,
        key="email_proposal_select"
    )


# ============================================================================
# 広告モード固有フォーム
# ============================================================================

def render_ads_mode_form() -> None:
    """広告モード固有フォーム"""
    st.markdown("### 📢 広告運用設定")

    st.session_state.form_data["platforms"] = st.multiselect(
        "配信プラットフォーム",
        ["Google Ads", "Facebook Ads", "Instagram Ads", "LinkedIn Ads", "TikTok Ads"],
        default=st.session_state.form_data.get("platforms", []),
        key="platforms_multiselect"
    )

    ad_file = st.file_uploader(
        "広告データCSV（任意）",
        type="csv",
        key="ad_data_upload"
    )
    if ad_file:
        ad_data = parse_ad_data(ad_file)
        st.session_state.uploaded_data["ad_data"] = ad_data
        st.success("✅ 広告データを読み込みました")

    st.session_state.form_data["monthly_budget"] = st.number_input(
        "月間予算（円）",
        min_value=0,
        value=st.session_state.form_data.get("monthly_budget", 100000),
        key="monthly_budget_input"
    )

    st.session_state.form_data["competitor_keywords"] = st.text_area(
        "競合URLまたはキーワード（改善対象を1行1つずつ）",
        value=st.session_state.form_data.get("competitor_keywords", ""),
        height=100,
        key="competitor_keywords_input"
    )


# ============================================================================
# LPモード固有フォーム
# ============================================================================

def render_lp_mode_form() -> None:
    """LPモード固有フォーム"""
    st.markdown("### 📄 ランディングページ設定")

    st.session_state.form_data["lp_url"] = st.text_input(
        "既存LPのURL（任意）",
        value=st.session_state.form_data.get("lp_url", ""),
        key="lp_url_input"
    )

    lp_screenshot = st.file_uploader(
        "LPのスクリーンショット（任意）",
        type=["png", "jpg", "jpeg"],
        key="lp_screenshot_upload"
    )
    if lp_screenshot:
        st.session_state.uploaded_data["lp_screenshot"] = lp_screenshot.getvalue()

    st.session_state.form_data["target_action"] = st.selectbox(
        "ターゲットアクション",
        ["", "購入", "資料請求", "お問い合わせ", "メルマガ登録"],
        index=0,
        key="target_action_select"
    )

    st.session_state.form_data["competitor_info"] = st.text_area(
        "競合URLまたはキーワード",
        value=st.session_state.form_data.get("competitor_info", ""),
        height=100,
        key="competitor_info_input"
    )


# ============================================================================
# CROモード固有フォーム
# ============================================================================

def render_cro_mode_form() -> None:
    """CROモード固有フォーム"""
    st.markdown("### 📊 CRO分析設定")

    st.session_state.form_data["site_type"] = st.selectbox(
        "サイトタイプ",
        ["", "BtoC", "BtoB", "EC"],
        index=0,
        key="site_type_select"
    )

    st.session_state.form_data["analysis_url"] = st.text_input(
        "分析対象URL（必須）",
        value=st.session_state.form_data.get("analysis_url", ""),
        key="analysis_url_input"
    )

    cro_screenshot = st.file_uploader(
        "スクリーンショット（推奨）",
        type=["png", "jpg", "jpeg"],
        key="cro_screenshot_upload"
    )
    if cro_screenshot:
        st.session_state.uploaded_data["cro_screenshot"] = cro_screenshot.getvalue()

    ga4_file = st.file_uploader(
        "GA4データCSV（任意）",
        type="csv",
        key="cro_ga4_csv_upload"
    )
    if ga4_file:
        ga4_data = parse_ga4_data(ga4_file)
        st.session_state.uploaded_data["ga4_data"] = ga4_data
        st.success("✅ GA4データを読み込みました")

    ad_file = st.file_uploader(
        "広告データCSV（任意）",
        type="csv",
        key="cro_ad_data_upload"
    )
    if ad_file:
        ad_data = parse_ad_data(ad_file)
        st.session_state.uploaded_data["ad_data"] = ad_data
        st.success("✅ 広告データを読み込みました")

    st.session_state.form_data["include_seo_analysis"] = st.checkbox(
        "SEO同時分析も行う",
        value=st.session_state.form_data.get("include_seo_analysis", False),
        key="include_seo_analysis_checkbox"
    )


# ============================================================================
# フォーム検証
# ============================================================================

def validate_form_data() -> tuple[bool, str]:
    """フォーム入力を検証"""
    form = st.session_state.form_data
    mode = st.session_state.current_mode

    # 共通必須項目
    if not form.get("industry"):
        return False, "業界/業種を入力してください"

    if not form.get("goal"):
        return False, "主な目的を選択してください"

    if not form.get("tone"):
        return False, "トーンを選択してください"

    # モード固有の検証
    if mode == "seo":
        if form.get("seo_submode") == "既存ページ改善" and not form.get("target_url"):
            return False, "対象ページのURLを入力してください"
        if form.get("seo_submode") == "新規ページ作成" and not form.get("target_keywords"):
            return False, "ターゲットキーワードを入力してください"

    elif mode == "email":
        if not form.get("email_proposal_type"):
            return False, "提案タイプを選択してください"

    elif mode == "ads":
        if not form.get("platforms"):
            return False, "配信プラットフォームを選択してください"

    elif mode == "lp":
        if not form.get("target_action"):
            return False, "ターゲットアクションを選択してください"

    elif mode == "cro":
        if not form.get("site_type"):
            return False, "サイトタイプを選択してください"
        if not form.get("analysis_url"):
            return False, "分析対象URLを入力してください"

    return True, ""


# ============================================================================
# 入力フォーム画面
# ============================================================================

def render_input_form(api_keys: dict) -> None:
    """入力フォーム画面"""
    mode_config = MODE_CONFIG.get(st.session_state.current_mode, {})
    mode_name = mode_config.get("name", "Unknown")

    st.markdown(f"## {mode_config.get('icon', '📝')} {mode_name}")
    st.markdown(mode_config.get("description", ""))
    st.divider()

    with st.form("input_form"):
        # 共通フォーム
        render_basic_info_form()
        st.divider()

        render_persona_form()
        st.divider()

        render_usp_competition_form()
        st.divider()

        render_image_generation_form()
        st.divider()

        # モード固有フォーム
        st.markdown(f"## {mode_config.get('icon')} モード固有設定")

        if st.session_state.current_mode == "seo":
            render_seo_mode_form()
        elif st.session_state.current_mode == "email":
            render_email_mode_form()
        elif st.session_state.current_mode == "ads":
            render_ads_mode_form()
        elif st.session_state.current_mode == "lp":
            render_lp_mode_form()
        elif st.session_state.current_mode == "cro":
            render_cro_mode_form()

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("◀ モード選択に戻る", use_container_width=True):
                st.session_state.current_mode = None
                st.session_state.form_data = {}
                st.rerun()

        with col2:
            if st.form_submit_button(
                "🚀 パイプライン開始",
                type="primary",
                use_container_width=True
            ):
                is_valid, error_msg = validate_form_data()
                if not is_valid:
                    st.error(f"❌ {error_msg}")
                else:
                    # APIキー検証
                    missing_keys = []
                    if not api_keys["anthropic"]:
                        missing_keys.append("Anthropic")
                    if not api_keys["openai"]:
                        missing_keys.append("OpenAI")
                    if not api_keys["gemini"]:
                        missing_keys.append("Gemini")

                    if missing_keys:
                        st.error(f"❌ 必要なAPIキーがありません: {', '.join(missing_keys)}")
                    else:
                        # パイプライン初期化
                        st.session_state.pipeline_state = PipelineState(
                            mode=st.session_state.current_mode,
                            form_data=st.session_state.form_data,
                            uploaded_data=st.session_state.uploaded_data,
                            api_keys=api_keys,
                            learning_data=st.session_state.learning_data
                        )
                        st.rerun()


# ============================================================================
# パイプライン実行画面
# ============================================================================

def render_pipeline_execution() -> None:
    """パイプライン実行画面"""
    pipeline = st.session_state.pipeline_state

    if pipeline is None:
        return

    mode_config = MODE_CONFIG.get(pipeline.mode, {})
    mode_name = mode_config.get("name", "Unknown")

    st.markdown(f"## {mode_config.get('icon')} {mode_name} - 実行中")
    st.divider()

    # 進捗表示
    total_steps = pipeline.total_steps
    current_step = pipeline.current_step
    progress = current_step / total_steps

    st.progress(progress, text=f"Step {current_step}/{total_steps}")

    # 各ステップ実行
    if not pipeline.is_completed():
        with st.spinner(f"Step {current_step}/{total_steps}: {pipeline.get_current_step_name()}中..."):
            try:
                result = execute_step(pipeline)
                pipeline.add_step_result(result)
                st.rerun()
            except Exception as e:
                st.error(f"❌ エラーが発生しました: {str(e)}")
                if st.button("このステップをやり直す"):
                    pipeline.reset_current_step()
                    st.rerun()

    # ステップ結果表示
    if pipeline.step_results:
        render_step_results(pipeline)

    # 完了後の処理
    if pipeline.is_completed():
        render_completion_screen(pipeline)


# ============================================================================
# ステップ結果表示
# ============================================================================

def render_step_results(pipeline: PipelineState) -> None:
    """ステップ結果表示"""
    if not pipeline.step_results:
        return

    latest_step = pipeline.step_results[-1]
    step_number = len(pipeline.step_results)

    st.markdown(f"### Step {step_number} 完了")

    # タブ表示
    if isinstance(latest_step, dict) and "results" in latest_step:
        results = latest_step["results"]
        tab_names = [
            f"🤖 {name}" for name in results.keys()
        ]

        tabs = st.tabs(tab_names)

        for tab, (ai_name, content) in zip(tabs, results.items()):
            with tab:
                st.markdown(content)

                # 修正・補足入力欄
                st.markdown("---")
                edit_key = f"edit_{step_number}_{ai_name}"
                user_edit = st.text_area(
                    "修正・補足（任意）",
                    key=edit_key,
                    height=100
                )

                if user_edit:
                    st.session_state.user_edits.append({
                        "step": step_number,
                        "ai": ai_name,
                        "edit": user_edit
                    })

    # ボタン
    col1, col2 = st.columns(2)
    with col1:
        if st.button("このステップをやり直す"):
            pipeline.reset_current_step()
            st.rerun()

    with col2:
        if st.button("この内容で次へ進む", type="primary"):
            pipeline.move_to_next_step()
            st.rerun()


# ============================================================================
# 完了画面
# ============================================================================

def render_completion_screen(pipeline: PipelineState) -> None:
    """完了画面"""
    st.markdown("## ✅ 分析完了！")
    st.divider()

    # 最終結果表示
    final_result = pipeline.get_final_result()
    if final_result:
        st.markdown(final_result)

    st.divider()

    # 品質チェックリスト
    st.markdown("### 📋 品質チェックリスト")
    checked_items = []
    for item in QUALITY_CHECKLIST:
        if st.checkbox(item):
            checked_items.append(item)

    st.divider()

    # 画像生成
    if pipeline.form_data.get("image_quality") != "OFF":
        st.markdown("### 🖼️ 画像生成")

        if st.button("画像を生成する"):
            with st.spinner("画像を生成中..."):
                try:
                    images = execute_image_generation(pipeline)
                    for idx, image_data in enumerate(images):
                        st.image(image_data, use_container_width=True)
                except Exception as e:
                    st.error(f"❌ 画像生成エラー: {str(e)}")

    st.divider()

    # ダウンロード・次のアクション
    st.markdown("### 📥 エクスポートと次のステップ")

    col1, col2 = st.columns(2)

    with col1:
        # Markdownレポート
        report_md = generate_markdown_report(pipeline, checked_items)
        st.download_button(
            label="📥 Markdownレポートをダウンロード",
            data=report_md.encode("utf-8"),
            file_name=f"report_{pipeline.mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
            use_container_width=True
        )

    with col2:
        # 学習データ
        learning_json = generate_session_json(pipeline, checked_items)
        st.download_button(
            label="💾 学習データをダウンロード",
            data=json.dumps(learning_json, ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"learning_{pipeline.mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            use_container_width=True
        )

    st.info(
        "💡 次回同じクライアントの案件で使う場合は、ダウンロードした学習データファイルを "
        "次のセッション開始時にアップロードしてください。スタイルの好みや修正パターンが "
        "自動的に反映されます。"
    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🔄 新しいセッションを開始", use_container_width=True):
            st.session_state.current_mode = None
            st.session_state.pipeline_state = None
            st.session_state.form_data = {}
            st.session_state.uploaded_data = {}
            st.rerun()

    with col2:
        if st.button("📊 別のモードでも分析する", use_container_width=True):
            # 結果をクロスモード保存
            st.session_state.cross_mode_results[pipeline.mode] = final_result
            st.session_state.current_mode = None
            st.session_state.pipeline_state = None
            st.rerun()

    # セッション履歴に保存
    session_record = {
        "timestamp": datetime.now().isoformat(),
        "mode": pipeline.mode,
        "client_name": pipeline.form_data.get("client_name", "Unknown"),
        "summary": final_result[:200] if final_result else "N/A"
    }
    st.session_state.session_history.append(session_record)


# ============================================================================
# フッター
# ============================================================================

def render_footer() -> None:
    """フッター"""
    st.divider()
    st.caption(
        "AI Marketing Studio v1.0.0 | "
        "Powered by Claude Sonnet 4, GPT-4o, Gemini 2.0 Flash"
    )


# ============================================================================
# メイン処理
# ============================================================================

def main() -> None:
    """メイン処理"""
    # 認証チェック
    check_password()

    # セッション初期化
    init_session_state()

    # サイドバー
    api_keys = render_sidebar()

    # メインエリア
    if st.session_state.pipeline_state is not None:
        # パイプライン実行画面
        render_pipeline_execution()
    elif st.session_state.current_mode is not None:
        # 入力フォーム画面
        render_input_form(api_keys)
    else:
        # モード選択画面
        render_mode_selection()

    # フッター
    render_footer()


if __name__ == "__main__":
    main()
