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


@dataclass
class PipelineState:
    """パイプラインの状態を管理するデータクラス"""
    mode: str
    current_step: int
    steps_completed: list[dict] = field(default_factory=list)
    user_edits: list[dict] = field(default_factory=list)
    is_complete: bool = False
    metadata: dict = field(default_factory=dict)


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
        構築されたメッセージ文字列
    """
    mode_config = MODE_CONFIG.get(mode, {})

    # ベースメッセージ
    base_info = f"""
クライアント: {form_data.get('client_name', '')}
業界: {form_data.get('industry', '')}
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

    # ステップ別の追加情報
    if step == 0:
        message += f"\nタスク: 初期分析を実施してください。{mode_config.get('step_0_prompt', '')}"
    elif step == 1 and previous_results:
        message += f"\n前のステップの分析結果:\n"
        for i, result in enumerate(previous_results):
            message += f"\n{i+1}. {result.get('ai_name', '')}: {result.get('content', '')[:500]}...\n"
        message += f"\nタスク: これらの分析を参考にして、コンテンツを生成してください。{mode_config.get('step_1_prompt', '')}"
    elif step == 2 and previous_results:
        message += f"\n前のステップの全結果:\n"
        for i, result in enumerate(previous_results):
            message += f"\n{i+1}. {result.get('ai_name', '')}: {result.get('content', '')[:300]}...\n"
        message += f"\nタスク: これらの結果を統合して、最終的な成果物を生成してください。{mode_config.get('step_2_prompt', '')}"

    return message


def execute_step(
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
    パイプラインのステップを実行

    Args:
        step: ステップ番号 (0, 1, 2)
        mode: モード名
        form_data: フォームデータ
        api_keys: APIキー辞書
        previous_results: 前のステップの結果
        uploaded_data: アップロードされたデータ
        competitor_data: 競合分析データ
        learning_data: 学習済みデータ
        progress_callback: 進捗コールバック関数

    Returns:
        ステップの結果リスト
    """
    if previous_results is None:
        previous_results = []

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
                "func": call_claude,
                "kwargs": {
                    "message": user_message,
                    "api_key": api_keys["anthropic"]
                }
            },
            {
                "name": "Gemini",
                "func": call_gemini,
                "kwargs": {
                    "message": user_message,
                    "api_key": api_keys["google"]
                }
            },
            {
                "name": "ChatGPT",
                "func": call_chatgpt,
                "kwargs": {
                    "message": user_message,
                    "api_key": api_keys["openai"]
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
                "content": result,
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
            message=user_message,
            api_key=api_keys["anthropic"]
        )
        results.append({
            "step": 1,
            "ai_name": "Claude",
            "content": claude_result,
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
            message=gemini_message,
            api_key=api_keys["google"]
        )
        results.append({
            "step": 1,
            "ai_name": "Gemini",
            "content": gemini_result,
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
            message=chatgpt_message,
            api_key=api_keys["openai"]
        )
        results.append({
            "step": 1,
            "ai_name": "ChatGPT",
            "content": chatgpt_result,
            "timestamp": None
        })
        if progress_callback:
            progress_callback("ChatGPT")

        return results

    elif step == 2:
        # Step 2: 統合 (Claudeで全結果を統合)
        integration_prompt = get_integration_prompt(mode, previous_results, form_data)

        claude_result = call_claude(
            message=integration_prompt,
            api_key=api_keys["anthropic"]
        )

        if progress_callback:
            progress_callback("Claude (Integration)")

        return [{
            "step": 2,
            "ai_name": "Claude",
            "content": claude_result,
            "timestamp": None,
            "is_integration": True
        }]

    return []


def execute_image_generation(
    mode: str,
    step_results: list[dict],
    form_data: dict,
    api_key: str,
    quality: str = "medium",
) -> list[dict]:
    """
    パイプライン完了後に画像生成を実行

    Args:
        mode: モード名
        step_results: パイプラインの全ステップ結果
        form_data: フォームデータ
        api_key: OPENAI APIキー
        quality: 画像品質 ("off", "medium", "high")

    Returns:
        生成された画像情報のリスト
    """
    if quality == "off":
        return []

    image_count = 1
    prompt_base = f"クライアント: {form_data.get('client_name', '')}, 業界: {form_data.get('industry', '')}"

    if mode == "SEO既存" or mode == "SEO新規":
        prompt = f"{prompt_base}\nアイキャッチ画像を生成してください。"
        image_count = 1
    elif mode == "広告":
        platform = form_data.get('platform', 'general')
        prompt = f"{prompt_base}\n{platform}用のバナー画像を生成してください。"
        image_count = 2 if quality == "high" else 1
    elif mode == "LP":
        prompt = f"{prompt_base}\nヒーロー画像とセクション画像を生成してください。"
        image_count = 2
    elif mode == "メール":
        prompt = f"{prompt_base}\nメールヘッダー画像を生成してください。"
        image_count = 1
    elif mode == "CRO":
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
        results.append({
            "type": "image",
            "mode": mode,
            "index": i + 1,
            "content": image_result,
            "prompt": prompt
        })

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
    """
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
