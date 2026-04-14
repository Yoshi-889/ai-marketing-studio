from dataclasses import dataclass, field
from typing import Callable, Optional
from config import MODE_CONFIG, QUALITY_CHECKLIST
from ai_clients import (
    call_claude,
    call_gemini,
    call_chatgpt,
    generate_image,
    run_parallel,
)


def suggest_target_keywords(
    keywords_data: list,
    api_keys: dict,
    context: str = ""
) -> str:
    """
    アップロードされたキーワードCSVからターゲットKWをAIが提案する

    Args:
        keywords_data: parse_keyword_csv() の結果リスト
        api_keys: APIキー辞書
        context: 業界・業種などのコンテキスト

    Returns:
        カンマ区切りの提案キーワード文字列
    """
    # 上位50件のキーワードを抽出
    kw_list = []
    for kw in keywords_data[:50]:
        if isinstance(kw, dict):
            keyword = kw.get("keyword") or kw.get("キーワード") or str(kw)
            volume = kw.get("volume") or kw.get("検索ボリューム") or kw.get("Volume") or ""
            difficulty = kw.get("difficulty") or kw.get("KD") or kw.get("競合性") or ""
            kw_list.append(f"{keyword} (ボリューム:{volume}, 難易度:{difficulty})")
        else:
            kw_list.append(str(kw))

    prompt = f"""以下のキーワードリストから、SEO・マーケティング観点で最も効果的なターゲットキーワードを5〜10個選んでください。

業界・コンテキスト: {context}

キーワードリスト:
{chr(10).join(kw_list)}

選定基準:
- 検索ボリュームと難易度のバランス
- ビジネス目標への関連性
- コンバージョン意図の高さ

出力形式（カンマ区切りのキーワードのみ、理由は不要）:
キーワード1, キーワード2, キーワード3, ...
"""

    result = call_claude(
        user_message=prompt,
        api_key=api_keys.get("anthropic", ""),
        system_prompt="あなたはSEOとコンテンツマーケティングの専門家です。キーワード選定のプロとして的確な提案を行ってください。",
    )
    # エラーの場合は空文字を返す
    if isinstance(result, dict) and "error" in result:
        return ""
    return str(result).strip()


class PipelineState:
    """パイプラインの状態を管理するクラス"""

    def __init__(
        self,
        mode: str,
        form_data: dict,
        uploaded_data: dict,
        api_keys: dict,
        learning_data: dict = None,
    ):
        self.mode = mode
        self.form_data = form_data
        self.uploaded_data = uploaded_data
        self.api_keys = api_keys
        self.learning_data = learning_data
        self.current_step: int = 1          # 1-indexed
        self.step_results: list = []        # results per completed step
        self._all_done: bool = False        # set True after user approves last step

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def total_steps(self) -> int:
        return len(MODE_CONFIG.get(self.mode, {}).get("steps", []))

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def is_completed(self) -> bool:
        """True once all steps have been executed and approved by the user."""
        return self._all_done or self.current_step > self.total_steps

    def has_current_step_result(self) -> bool:
        """True if the current step has already produced a result (prevents re-execution)."""
        return len(self.step_results) >= self.current_step

    def get_current_step_name(self) -> str:
        steps = MODE_CONFIG.get(self.mode, {}).get("steps", [])
        idx = self.current_step - 1
        if 0 <= idx < len(steps):
            return steps[idx].get("name", f"ステップ{self.current_step}")
        return "完了"

    def get_final_result(self) -> str:
        """Return the integration (last-step) result as a markdown string."""
        if not self.step_results:
            return ""
        last = self.step_results[-1]
        if isinstance(last, dict) and "results" in last:
            parts = []
            for ai_name, content in last["results"].items():
                parts.append(f"### {ai_name}\n\n{content}")
            return "\n\n---\n\n".join(parts)
        return str(last)

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    def add_step_result(self, result: dict) -> None:
        """Append the result produced by execute_step for the current step."""
        # Remove any stale result at this position (e.g. after a reset)
        while len(self.step_results) >= self.current_step:
            self.step_results.pop()
        self.step_results.append(result)

    def reset_current_step(self) -> None:
        """Drop the current step's result so the step can be re-executed."""
        while len(self.step_results) >= self.current_step:
            self.step_results.pop()
        self._all_done = False

    def move_to_next_step(self) -> None:
        """Approve current step result and advance to the next step."""
        self.current_step += 1
        if self.current_step > self.total_steps:
            self._all_done = True


# ===========================================================================
# Internal helpers
# ===========================================================================

def build_user_message(
    mode: str,
    form_data: dict,
    step: int,
    previous_results: list[dict] = None,
    uploaded_data: dict = None,
    competitor_data: dict = None,
    learning_data: dict = None,
) -> str:
    """
    各AIへのユーザーメッセージを構築

    Args:
        mode: モード名
        form_data: フォームデータ
        step: ステップ番号 (0, 1, 2)
        previous_results: 前のステップの結果
        uploaded_data: アップロードされたデータ
        competitor_data: 競合分析データ
        learning_data: 学習済みデータ

    Returns:
        構築され�メッセージ文字列
    """
    mode_config = MODE_CONFIG.get(mode, {})

    # ベースメッセージ
    base_info = f"""
クライアント: {form_data.get('client_name', '')}
業界: {form_data.get('industry', '')}
ターゲットキーワード: {form_data.get('target_keywords', '')}
ターゲットペルソナ: {form_data.get('target_persona', '')}
USP: {form_data.get('usp', '')}
競合: {form_data.get('competitors', '')}
目標: {form_data.get('goal', '')}
トーン: {form_data.get('tone', 'プロフェッショナル')}
"""

    # モード固有の情報
    mode_specific = ""
    if mode == "SEO既存":
        mode_specific = f"対象URL: {form_data.get('url', '')}\n"
    elif mode == "SEO新規":
        mode_specific = f"キーワード: {form_data.get('keywords_data', '')}\n"
    elif mode == "広告":
        mode_specific = f"プラットフォーム: {form_data.get('platform', '')}\n"
    elif mode == "メール":
        mode_specific = f"メール数: {form_data.get('email_count', '')}\n"
    elif mode == "CRO":
        mode_specific = f"サイトタイプ: {form_data.get('site_type', '')}\n"

    message = base_info + mode_specific

    # アップロードデータのサマリー
    if uploaded_data:
        if "keywords" in uploaded_data:
            message += f"\nキーワードデータ: {len(uploaded_data['keywords'])}件\n"
        if "ga4_data" in uploaded_data:
            message += f"GA4データ: {uploaded_data['ga4_data'].get('summary', '')}\n"

    # 競合分析データ
    if competitor_data:
        message += f"\n競合分析:\n"
        for competitor, analysis in competitor_data.items():
            message += f"- {competitor}: {analysis.get('summary', '')}\n"

    # 学習データ
    if learning_data:
        if "style_guidelines" in learning_data:
            message += f"\nスタイルガイドライン: {learning_data['style_guidelines']}\n"
        if "ng_expressions" in learning_data:
            message += f"NG表現: {', '.join(learning_data['ng_expressions'])}\n"

    # ステップ別の追加情報（パネルディスカッション形式）
    if step == 0:
        message += f"\n---\n【パネルディスカッション Round 1】\nあなたはマーケティング専門家パネリストの一人です。他のAIパネリストとは独立して、あなた固有の視点・専門性で分析を行ってください。\nタスク: {mode_config.get('step_0_prompt', '初期分析を実施してください。')}"
    elif step == 1 and previous_results:
        message += f"\n---\n【パネルディスカッション Round 2】\n前のパネリストたちの分析を踏まえ、あなたの意見を述べてください。同意・補足・異なる視点があれば明確に示してください。\n\n前のパネリストの意見:\n"
        for i, result in enumerate(previous_results):
            message += f"\n■ {result.get('ai_name', f'パネリスト{i+1}')}の意見:\n{result.get('content', '')[:600]}\n"
        message += f"\nタスク: 上記を踏まえてコンテンツを生成し、各パネリストとの相違点・共通点も述べてください。{mode_config.get('step_1_prompt', '')}"
    elif step == 2 and previous_results:
        message += f"\n---\n【パネルディスカッション 統合フェーズ】\n全パネリストの議論を整理し、最終的なコンセンサスと推奨事項をまとめてください。\n\n全パネリストの意見:\n"
        for i, result in enumerate(previous_results):
            message += f"\n■ {result.get('ai_name', f'パネリスト{i+1}')}:\n{result.get('content', '')[:400]}\n"
        message += f"\nタスク: 議論を統合し、最終成果物を生成してください。{mode_config.get('step_2_prompt', '')}"

    return message


def _flatten_previous_results(step_results: list) -> list[dict]:
    """Convert step_results (list of {"results": {...}}) to a flat list of {"ai_name", "content"}."""
    flat = []
    for step_result in step_results:
        if isinstance(step_result, dict) and "results" in step_result:
            for ai_name, content in step_result["results"].items():
                flat.append({"ai_name": ai_name, "content": content})
    return flat


def _extract_content(result) -> str:
    """AI APIのレスポンスdictから文字列コンテンツを取り出す。"""
    if isinstance(result, dict):
        content = result.get("content", "")
        if not result.get("success", True):
            return f"❌ エラー: {content}"
        return content if isinstance(content, str) else str(content)
    return str(result)


def _run_step_raw(
    step: int,
    mode: str,
    form_data: dict,
    api_keys: dict,
    previous_results: list[dict] = None,
    uploaded_data: dict = None,
    competitor_data: dict = None,
    learning_data: dict = None,
    progress_callback: Callable = None,
) -> list[dict]:
    """
    パイプラインのステップを実行（内部関数）

    Returns:
        list[dict] with keys: step, ai_name, content, timestamp
    """
    if previous_results is None:
        previous_results = []

    roles = MODE_CONFIG.get(mode, {}).get("roles", {})

    if step == 0:
        # Step 0: 並列実行で3つの分析を実行
        user_message = build_user_message(
            mode, form_data, step,
            uploaded_data=uploaded_data,
            competitor_data=competitor_data,
            learning_data=learning_data
        )

        tasks = [
            {
                "name": "Claude",
                "fn": call_claude,
                "kwargs": {
                    "user_message": user_message,
                    "api_key": api_keys["anthropic"],
                    "system_prompt": roles.get("claude", {}).get("system_prompt", ""),
                }
            },
            {
                "name": "Gemini",
                "fn": call_gemini,
                "kwargs": {
                    "user_message": user_message,
                    "api_key": api_keys["gemini"],
                    "system_prompt": roles.get("gemini", {}).get("system_prompt", ""),
                }
            },
            {
                "name": "ChatGPT",
                "fn": call_chatgpt,
                "kwargs": {
                    "user_message": user_message,
                    "api_key": api_keys["openai"],
                    "system_prompt": roles.get("chatgpt", {}).get("system_prompt", ""),
                }
            }
        ]

        results = run_parallel(
            tasks,
            progress_callback=progress_callback
        )

        formatted_results = []
        ai_names = ["Claude", "Gemini", "ChatGPT"]
        for i, result in enumerate(results):
            formatted_results.append({
                "step": 0,
                "ai_name": ai_names[i],
                "content": _extract_content(result),
                "timestamp": None
            })

        return formatted_results

    elif step == 1:
        # Step 1: リレー方式 Claude → Gemini → ChatGPT
        results = []

        # Claude
        user_message = build_user_message(
            mode, form_data, step,
            previous_results=previous_results,
            uploaded_data=uploaded_data,
            competitor_data=competitor_data,
            learning_data=learning_data
        )

        claude_result = call_claude(
            user_message=user_message,
            api_key=api_keys["anthropic"],
            system_prompt=roles.get("claude", {}).get("system_prompt", ""),
        )
        results.append({
            "step": 1,
            "ai_name": "Claude",
            "content": _extract_content(claude_result),
            "timestamp": None
        })
        if progress_callback:
            progress_callback("Claude")

        # Gemini (Claudeの結果を参考に)
        gemini_message = build_user_message(
            mode, form_data, step,
            previous_results=previous_results + results,
            uploaded_data=uploaded_data,
            competitor_data=competitor_data,
            learning_data=learning_data
        )

        gemini_result = call_gemini(
            user_message=gemini_message,
            api_key=api_keys["gemini"],
            system_prompt=roles.get("gemini", {}).get("system_prompt", ""),
        )
        results.append({
            "step": 1,
            "ai_name": "Gemini",
            "content": _extract_content(gemini_result),
            "timestamp": None
        })
        if progress_callback:
            progress_callback("Gemini")

        # ChatGPT (Claude + Gemimiの結果を参考に)
        chatgpt_message = build_user_message(
            mode, form_data, step,
            previous_results=previous_results + results,
            uploaded_data=uploaded_data,
            competitor_data=competitor_data,
            learning_data=learning_data
        )

        chatgpt_result = call_chatgpt(
            user_message=chatgpt_message,
            api_key=api_keys["openai"],
            system_prompt=roles.get("chatgpt", {}).get("system_prompt", ""),
        )
        results.append({
            "step": 1,
            "ai_name": "ChatGPT",
            "content": _extract_content(chatgpt_result),
            "timestamp": None
        })
        if progress_callback:
            progress_callback("ChatGPT")

        return results

    elif step == 2:
        # Step 2: 統合 (Claudeで全結果を統合)
        integration_prompt = get_integration_prompt(mode, previous_results, form_data)

        claude_result = call_claude(
            user_message=integration_prompt,
            api_key=api_keys["anthropic"],
            system_prompt=roles.get("claude", {}).get("system_prompt", ""),
           )

        if progress_callback:
            progress_callback("Claude (Integration)")

        return [{
            "step": 2,
            "ai_name": "Claude",
            "content": _extract_content(claude_result),
            "timestamp": None,
            "is_integration": True
        }]

    return []


# ===========================================================================
# Public API — these are the functions imported by app.py
# ===========================================================================

def execute_step(pipeline: "PipelineState") -> dict:
    """
    Execute the current step of the pipeline.

    Args:
        pipeline: PipelineState object

    Returns:
        dict with key "results": {ai_name: content_str}
    """
    step_index = pipeline.current_step - 1  # convert 1-indexed → 0-indexed
    previous_flat = _flatten_previous_results(pipeline.step_results)

    raw = _run_step_raw(
        step=step_index,
        mode=pipeline.mode,
        form_data=pipeline.form_data,
        api_keys=pipeline.api_keys,
        previous_results=previous_flat,
        uploaded_data=pipeline.uploaded_data,
        learning_data=pipeline.learning_data,
    )

    return {"results": {r["ai_name"]: r["content"] for r in raw}}


def execute_image_generation(pipeline: "PipelineState") -> list:
    """
    画像生成を実行する。

    Args:
        pipeline: PipelineState object

    Returns:
        list of image data (bytes or base64 strings)
    """
    mode = pipeline.mode
    form_data = pipeline.form_data
    api_key = pipeline.api_keys.get("openai", "")
    quality = form_data.get("image_quality", "medium").lower()

    if quality == "off":
        return []

    image_count = 1
    prompt_base = f"クライアント: {form_data.get('client_name', '')}, 業界: {form_data.get('industry', '')}"

    if mode in ("SEO既存", "SEO新規", "seo"):
        prompt = f"{prompt_base}\nアイキャッチ画像を生成してください。"
        image_count = 1
    elif mode in ("広告", "ads"):
        platform = form_data.get('platform', 'general')
        prompt = f"{prompt_base}\n{platform}用のバナー画像を生成してください。"
        image_count = 2 if quality == "high" else 1
    elif mode in ("LP", "lp"):
        prompt = f"{prompt_base}\nヒーロー画像とセクション画像を生成してください。"
        image_count = 2
    elif mode in ("メール", "email"):
        prompt = f"{prompt_base}\nメールヘッダー画像を生成してください。"
        image_count = 1
    elif mode in ("CRO", "cro"):
        prompt = f"{prompt_base}\n改善案のモックアップイメージを生成してください。"
        image_count = 1
    else:
        prompt = f"{prompt_base}\n関連画像を生成してください。"

    results = []
    for i in range(image_count):
        image_result = generate_image(
            prompt=prompt,
            api_key=api_key,
            quality=quality
        )
        results.append(image_result)

    return results


def get_integration_prompt(mode: str, all_results: list[dict], form_data: dict) -> str:
    """
    Step 2用の統合プロンプトを生成

    Args:
        mode: モード名
        all_results: 全ステップの結果
        form_data: フォームデータ

    Returns:
        統合プロンプト文字列
    """
    mode_config = MODE_CONFIG.get(mode, {})

    prompt = f"""
以下のパイプライン実行結果を参照して、最終的な統合された成果物を生成してください。

クライアント情報:
- クライアント: {form_data.get('client_name', '')}
- 業界: {form_data.get('industry', '')}
- ターゲット: {form_data.get('target_persona', '')}
- USP: {form_data.get('usp', '')}

これまでの分析・生成結果:
"""

    for result in all_results:
        prompt += f"\n【{result.get('ai_name', '')}: ステップ{result.get('step', '')}】\n"
        prompt += result.get('content', '')[:1000] + "\n"

    prompt += f"\n{mode_config.get('integration_prompt', '')}\n\n"

    prompt += "品質チェックリスト:\n"
    for i, checklist_item in enumerate(QUALITY_CHECKLIST.get(mode, []), 1):
        prompt += f"{i}. {checklist_item}\n"

    prompt += "\n上記の品質チェックリストに基づいて、最終成果物を生成してください。"

    return prompt


def format_step_results(results: list[dict], step: int) -> str:
    """
    ステップの結果をMarkdown形式に整形

    Args:
        results: ステップの結果リスト
        step: ステップ番号

    Returns:
        Markdown形式の整形結果
   2"""
    ai_icons = {
        "Claude": "🤖",
        "Gemini": "✨",
        "ChatGPT": "💡"
    }

    output = f"## ステップ {step} の結果\n\n"

    for result in results:
        ai_name = result.get('ai_name', '不明')
        icon = ai_icons.get(ai_name, "📝")

        output += f"### {icon} {ai_name}\n\n"
        output += f"**役割:** {ai_name}による分析\n\n"
        output += f"```\n{result.get('content', '')}\n```\n\n"

    return output
