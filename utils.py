import pandas as pd
import json
import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Tuple

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


def parse_keyword_csv(uploaded_file) -> dict:
    """
    Streamlitのupload_fileオブジェクトからキーワードCSV/TSVを解析する。

    Args:
        uploaded_file: Streamlit upload_file オブジェクト

    Returns:
        {
            "success": bool,
            "data": pd.DataFrame or None,
            "columns": list,
            "error": str or None
        }
    """
    try:
  2     if uploaded_file is None:
            return {
                "success": False,
                "data": None,
                "columns": [],
                "error": "ファイルがアップロードされていません"
            }

        # ファイル内容を読み込み
        content = uploaded_file.getvalue().decode('utf-8')

        # CSV/TSV判別
  2     if '\t' in content.split('\n')[0]:
            df = pd.read_csv(io.StringIO(content), sep='\t')
        else:
            df = pd.read_csv(io.StringIO(content))

        if df.empty:
            return {
                "success": False,
                "data": None,
                "columns": [],
                "error": "CSVファイルが空です"
            }

        # キーワード列を自動検出
        keyword_col = None
        keyword_candidates = ["Keyword", "キーワード", "keyword", "検索語句", "keyword_text", "search_term"]

        for col in keyword_candidates:
            if col in df.columns:
                keyword_col = col
                break

        if keyword_col is None:
            # 最初の列をキーワード列として扱う
            keyword_col = df.columns[0]

        return {
            "success": True,
            "data": df,
            "columns": list(df.columns),
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "data": None,
            "columns": [],
            "error": f"CSVファイルの解析に失敗しました: {str(e)}"
        }


def parse_ga4_data(uploaded_file) -> dict:
    """
    GA4エクスポートデータ（CSV）を解析する。

    Args:
        uploaded_file: Streamlit upload_file オブジェクト

    Returns:
        {
            "success": bool,
            "data": pd.DataFrame or None,
            "summary": dict,
            "error": str or None
        }
    """
    try:
        if uploaded_file is None:
            return {
                "success": False,
                "data": None,
                "summary": {},
                "error": "ファイルがアップロードされていません"
            }

        content = uploaded_file.getvalue().decode('utf-8')
        df = pd.read_csv(io.StringIO(content))

        if df.empty:
            return {
                "success": False,
                "data": None,
                "summary": {},
                "error": "GA4ファイルが空です"
            }

        # カラム名の正規化
        df.columns = df.columns.str.strip()

        # 必要なカラムを抽出
 2      summary = {
            "total_sessions": 0,
            "total_revenue": 0.0,
            "avg_conversion_rate": 0.0,
            "page_count": len(df)
        }

        # セッション数を抽出
        if "Sessions" in df.columns:
            summary["total_sessions"] = int(df["Sessions"].sum())
        elif "セッション" in df.columns:
            summary["total_sessions"] = int(df["セッション"].sum())

        # 収益を抽出
        if "Revenue" in df.columns:
            summary["total_revenue"] = float(df["Revenue"].sum())
        elif "収益" in df.columns:
            summary["total_revenue"] = float(df["収益"].sum())

        # コンバージョン率を抽出
        if "Conversion rate" in df.columns:
            summary["avg_conversion_rate"] = float(df["Conversion rate"].mean())
        elif "コンバージョン率" in df.columns:
            summary["avg_conversion_rate"] = float(df["コンバージョン率"].mean())

        return {
            "success": True,
            "data": df,
            "summary": summary,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "data": None,
            "summary": {},
            "error": f"GA4ファイルの解析に失敗しました: {str(e)}"
        }


def parse_ad_data(uploaded_file) -> dict:
    """
    広告プラットフォーム（Google Ads, Facebook Ads）のCSVデータを解析する。

    Args:
        uploaded_file: Streamlit upload_file オブジェクト

    Returns:
        {
            "success": bool,
            "data": pd.DataFrame or None,
            "summary": dict,
            "error": str or None
        }
    """
    try:
        if uploaded_file is None:
            return {
                "success": False,
                "data": None,
                "summary": {},
                "error": "ファイルがアップロードされていません"
            }

        content = uploaded_file.getvalue().decode('utf-8')
        df = pd.read_csv(io.StringIO(content))

        if df.empty:
            return {
                "success": False,
                "data": None,
                "summary": {},
                "error": "広告ファイルが空です"
            }

        # カラム名の正規化
        df.columns = df.columns.str.strip()

        # サマリーの初期化
        summary = {
            "total_clicks": 0,
            "total_impressions": 0,
            "total_cost": 0.0,
            "total_conversions": 0,
            "avg_roas": 0.0,
            "campaign_count": 0
        }

        # クリック数
        if "Clicks" in df.columns:
            summary["total_clicks"] = int(df["Clicks"].sum())
        elif "クリック数" in df.columns:
            summary["total_clicks"] = int(df["クリック数"].sum())

        # 表示回数
        if "Impressions" in df.columns:
            summary["total_impressions"] = int(df["Impressions"].sum())
        elif "表示回数" in df.columns:
            summary["total_impressions"] = int(df["表示回数"].sum())

        # 費用
        if "Cost" in df.columns:
            summary["total_cost"] = float(df["Cost"].sum())
        elif "費用" in df.columns:
            summary["total_cost"] = float(df["費用"].sum())

        # コンバージョン
        if "Conversions" in df.columns:
            summary["total_conversions"] = int(df["Conversions"].sum())
        elif "コンバージョン数" in df.columns:
            summary["total_conversions"] = int(df["コンバージョン数"].sum())

        # ROAS
        if "ROAS" in df.columns:
            roas_values = pd.to_numeric(df["ROAS"], errors='coerce')
            summary["avg_roas"] = float(roas_values.mean())
        elif "ROAS（目標値）" in df.columns:
            roas_values = pd.to_numeric(df["ROAS（目標値）"], errors='coerce')
            summary["avg_roas"] = float(roas_values.mean())

        # キャンペーン数
        if "Campaign" in df.columns:
            summary["campaign_count"] = df["Campaign"].nunique()
        elif "キャンペーン" in df.columns:
            summary["campaign_count"] = df["キャンペーン"].nunique()

        return {
            "success": True,
            "data": df,
            "summary": summary,
            "error": None
        }

    except Exception as e:
        return {
            "success": False,
            "data": None,
            "summary": {},
            "error": f"広告ファイルの解析に失敗しました: {str(e)}"
        }


def extract_text_from_pdf(uploaded_file) -> str:
    """
    PDFからテキストをڊ�出する。

    Args:
        uploaded_file: Streamlit upload_file オブジェクト

    Returns:
        抽出されたテキスト（最大10000文字）
    """
    try:
        if uploaded_file is None:
            return ""

        text = ""

        # pdfplumberを優先的に使用
        if HAS_PDFPLUMBER:
            import pdfplumber
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
        elif HAS_PYPDF2:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            for page in pdf_reader.pages:
                text += page.extract_text()
        else:
            return "PDFライブラリが利用できません"

        # テキスト長をチェック
        if len(text.strip()) < 100:
            text += "\n\n【警告】テキストが少ないため、画像ベースのPDFの可能性があります。"

        # 最大10000文字に制限
        return text[:10000]

    except Exception as e:
        return f"PDFの抽出に失敗しました: {str(e)}"


def extract_newsletter_analysis(text: str) -> dict:
    """
    メルマガのテキストから以下を分析する。

    Args:
        text: メルマガのテキスト

    Returns:
        {
            "tone": str,
            "style_features": list,
            "layout_structure": str,
            "appeal_patterns": list
        }
    """
    if not text or len(text.strip()) == 0:
        return {
            "tone": "不明",
            "style_features": [],
            "layout_structure": "不明",
            "appeal_patterns": []
        }

    # トーンの推定
    tone = "フォーマル"
    casual_indicators = ["です！", "ですね", "でしょう？", "だよ", "って感じ"]
    casual_count = sum(1 for indicator in casual_indicators if indicator in text)

    if casual_count > 2:
        tone = "カジュアル"

    # 文体の特徴を抽出
    style_features = []

    if "【" in text and "】" in text:
        style_features.append("見出しに装飾括弧を使用")

    if "□" in text or "✓" in text or "●" in text:
        style_features.append("箇条書きを使用")

    if text.count("\n") > 20:
        style_features.append("短段落を多用")

    if "👇" in text or "👉" in text or "💡" in text:
        style_features.append("絵文字を使用")

    # レイアウト構造の推定
    lines = text.split('\n')
    layout_structure = "標準的"

    if len(lines) > 50:
        layout_structure = "詳細な多セクション構成"
    elif len(lines) > 20:
        layout_structure = "複数セクション構成"

    # 訴求パターンを抽出
    appeal_patterns = []

    if any(word in text for word in ["限定", "今だけ", "期間限定", "先着"]):
        appeal_patterns.append("希少性訴求")

    if any(word in text for word in ["メリット", "効果", "成功", "実績", "成果"]):
        appeal_patterns.append("ベネフィット訴求")

    if any(word in text for word in ["確認", "チェック", "クリック", "詳細は", "こちら"]):
        appeal_patterns.append("CTA（行動喚起）")

    if any(word in text for word in ["無料", "お得", "割引", "セール"]):
        appeal_patterns.append("価値提供訴求")

    return {
        "tone": tone,
        "style_features": style_features if style_features else ["標準的"],
        "layout_structure": layout_structure,
        "appeal_patterns": appeal_patterns if appeal_patterns else ["標準的"]
    }


def generate_markdown_report(pipeline, checked_items: list) -> str:
    """
    パイプライン結果をMarkdownレポートに変換する。

    Args:
        pipeline: PipelineState オブジェクト
        checked_items: 品質チェックリストでチェックされた項目

    Returns:
        Markdown形式のレポート文字列
    """
    from datetime import datetime as _dt
    from config import MODE_CONFIG

    mode = pipeline.mode
    form_data = pipeline.form_data
    mode_config = MODE_CONFIG.get(mode, {})
    mode_name = mode_config.get("name", mode)

    report = []

    # ヘッダー
    report.append("# AI Marketing Studio レポート\n")
    report.append(f"**クライアント:** {form_data.get('client_name', '')}\n")
    report.append(f"**作成日:** {_dt.now().strftime('%Y年%m月%d日')}\n")
    report.append(f"**分析モード:** {mode_name}\n")
    report.append("\n---\n")

    # 各ステップの結果
    step_names = [s.get("name", f"ステップ{i+1}") for i, s in enumerate(mode_config.get("steps", []))]
    for i, step_result in enumerate(pipeline.step_results):
        step_label = step_names[i] if i < len(step_names) else f"ステップ{i+1}"
        report.append(f"\n## ステップ {i+1}: {step_label}\n")

        if isinstance(step_result, dict) and "results" in step_result:
            for ai_name, content in step_result["results"].items():
                report.append(f"\n### {ai_name}\n")
                report.append(f"{content}\n")

        report.append("\n---\n")

    # 品質チェックリスト
    if checked_items:
        report.append("\n## 品質チェックリスト\n")
        for item in checked_items:
            report.append(f"- ✅ {item}\n")

    return "\n".join(report)


def generate_session_json(pipeline, checked_items: list) -> dict:
    """
    セッション全体のデータをJSON辞書に変換する。

    Args:
        pipeline: PipelineState オブジェクト
        checked_items: 品質チェックリストでチェックされた項目

    Returns:
        セッションデータの辞書
    """
    from datetime import datetime as _dt

    steps_export = []
    for i, step_result in enumerate(pipeline.step_results):
        if isinstance(step_result, dict) and "results" in step_result:
            steps_export.append({
                "step": i + 1,
                "results": step_result["results"]
            })
        else:
            steps_export.append({"step": i + 1, "results": str(step_result)})

    return {
        "timestamp": _dt.now().isoformat(),
        "mode": pipeline.mode,
        "form_data": pipeline.form_data,
        "steps": steps_export,
        "quality_checklist": checked_items,
        "learning_data": pipeline.learning_data or {},
    }


def create_learning_data(
    session_data: dict,
    user_edits: list[dict],
    style_preferences: dict
) -> dict:
    """
    セッション情報、ユーザーの修正履歴、スタイル設定を統合して学習データを生成する。

    Args:
        session_data: セッション全体のデータ
        user_edits: ユーザーの修正履歴のリスト
        style_preferences: スタイル設定（トーン、NG表現、好みの表現等）

    Returns:
        学習データの辞書
    """
    now = datetime.now().isoformat()

    return {
        "version": "1.0",
        "created_at": now,
        "client_name": session_data.get("client_name", ""),
        "mode": session_data.get("mode", ""),
        "style_preferences": style_preferences,
        "edit_history": user_edits,
        "context": {
            "industry": session_data.get("industry", ""),
            "target_audience": session_data.get("target_audience", ""),
            "business_type": session_data.get("business_type", "")
        }
    }


def load_learning_data(uploaded_file) -> dict:
    """
    JSONファイルを読み込んで学習データを復元する。

    Args:
        uploaded_file: Streamlit upload_file オブジェクト

    Returns:
        {
            "success": bool,
            "data": dict or None,
            "error": str or None
        }
    """
    try:
        if uploaded_file is None:
            return {
                "success": False,
                "data": None,
                "error": "ファイルがアップロードされていません"
            }

        content = uploaded_file.getvalue().decode('utf-8')
        data = json.loads(content)

        # バージョンチェック
        if "version" not in data:
            return {
                "success": False,
                "data": None,
                "error": "学習データのバージョン情報がありません"
            }

        # 互換性チェック（現在のバージョンは1.0）
        version = data.get("version", "1.0")
        if version != "1.0":
            return {
                "success": False,
                "data": None,
                "error": f"互換性のないバージョンです: {version}"
            }

        return {
            "success": True,
            "data": data,
            "error": None
        }

    except json.JSONDecodeError:
        return {
            "success": False,
            "data": None,
            "error": "JSONファイルが無効です"
        }
    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"ファイルの読み込みに失敗しました: {str(e)}"
        }


def create_before_after_table(before: str, after: str) -> str:
    """
    ビフォーアフターをMarkdownテーブルで生成する。

    Args:
        before: 変更前のテキスト
        after: 変更後のテキスト

    Returns:
        Markdown形式のテーブル
    """
    # 簡単な差分判定
    before_lines = before.split('\n')
    after_lines = after.split('\n')

    max_lines = max(len(before_lines), len(after_lines))

    # テーブルヘッダー
    table = "| 変更前 | 変更後 |\n"
    table += "|--------|--------|\n"

    # 各行を比較
    for i in range(max_lines):
        before_text = before_lines[i] if i < len(before_lines) else ""
        after_text = after_lines[i] if i < len(after_lines) else ""

        # 差分がある場合は太字で表示
        if before_text != after_text:
            before_display = f"**{before_text}**" if before_text else ""
            after_display = f"**{after_text}**" if after_text else ""
        else:
            before_display = before_text
            after_display = after_text

        table += f"| {before_display} | {after_display} |\n"

    return table


def summarize_page_data(data: pd.DataFrame) -> str:
    """
    GA4ページデータのサマリーを生成する。
    改善で伸びが期待できるサイト上位5つを自動抽出（アクセスあるが収益が低いページ）。

    Args:
        data: GA4ページデータのDataFrame

    Returns:
        Markdown形式のサマリー
    """
    try:
        if data.empty:
            return "## ページデータサマリー\n\nデータが利用できません。"

        summary = []
        summary.append("## ページデータサマリー\n")

        # 基本統計
        if "Sessions" in data.columns or "セッション" in data.columns:
            sessions_col = "Sessions" if "Sessions" in data.columns else "セッション"
            total_sessions = int(data[sessions_col].sum())
            summary.append(f"**総セッション数:** {total_sessions:,}\n")

        if "Revenue" in data.columns or "収益" in data.columns:
            revenue_col = "Revenue" if "Revenue" in data.columns else "収益"
            total_revenue = float(data[revenue_col].sum())
            summary.append(f"**総収益:** ¥{total_revenue:,.0f}\n")

        summary.append("\n### 改善の機会が高いページ（上位5）\n")
        summary.append("アクセスはあるが収益が低いページを抽出:\n\n")

        # スコアリング用の準備
        scoring_data = data.copy()

        # セッション数とREVENUEで正規化スコア計算
        sessions_col = None
        revenue_col = None
        url_col = None

        for col in ["Sessions", "セッション", "PagePath", "ページパス", "Page"]:
            if col in data.columns:
                if col in ["Sessions", "セッション"]:
                    sessions_col = col
                elif col in ["PagePath", "ページパス", "Page"]:
                    url_col = col

        for col in ["Revenue", "収益"]:
            if col in data.columns:
                revenue_col = col
                break

        if sessions_col and revenue_col:
            # セッション数が多く、収益が低いページを特定
            scoring_data['sessions_numeric'] = pd.to_numeric(
                scoring_data[sessions_col], errors='coerce'
            ).fillna(0)
            scoring_data['revenue_numeric'] = pd.to_numeric(
                scoring_data[revenue_col], errors='coerce'
            ).fillna(0)

            # スコア計算（セッションは多い、収益は少ない）
            scoring_data['opportunity_score'] = (
                scoring_data['sessions_numeric'] / (scoring_data['revenue_numeric'] + 1)
            )

            # 上位5件を取得
            top_5 = scoring_data.nlargest(5, 'opportunity_score')

            for idx, (_, row) in enumerate(top_5.iterrows(), 1):
                page = row.get(url_col, f"ページ {idx}") if url_col else f"ページ {idx}"
                sessions = int(row['sessions_numeric'])
                revenue = float(row['revenue_numeric'])

                summary.append(f"{idx}. **{page}**\n")
                summary.append(f"   - セッション: {sessions:,}\n")
                summary.append(f"   - 収益: ¥{revenue:,.0f}\n")
                summary.append(f"   - 改善優先度: 高\n\n")

        return "\n".join(summary)

    except Exception as e:
        return f"## ページデータサマリー\n\nサマリー生成に失敗しました: {str(e)}"
