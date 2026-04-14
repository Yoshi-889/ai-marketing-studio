import anthropic
import google.genai as genai
import openai
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional
import base64
from io import BytesIO


def call_claude(
    api_key: str,
    system_prompt: str,
    user_message: str,
    role_name: str = "",
    temperature: float = 0.5,
) -> dict[str, Any]:
    """
    ClaudeのAPIを呼び出す関数

    Args:
        api_key: AnthropicのAPIキー
        system_prompt: システムプロンプト
        user_message: ユーザーメッセージ
        role_name: このAIの役割名
        temperature: 温度パラメータ

    Returns:
        APIレスポンスとメタデータを含む辞書
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
        )
        return {
            "name": "Claude",
            "icon": "🟣",
            "success": True,
            "content": message.content[0].text,
            "model": "claude-sonnet-4-20250514",
            "role": role_name,
        }
    except Exception as e:
        return {
            "name": "Claude",
            "icon": "🟣",
            "success": False,
            "content": f"エラー: {str(e)}",
            "model": "claude-sonnet-4-20250514",
            "role": role_name,
        }


def call_gemini(
    api_key: str,
    system_prompt: str,
    user_message: str,
    role_name: str = "",
    temperature: float = 0.7,
) -> dict[str, Any]:
    """
    GeminiのAPIを呼び出す関数

    Args:
        api_key: GoogleのAPIキー
        system_prompt: システムプロンプト
        user_message: ユーザーメッセージ
        role_name: このAIの役割名
        temperature: 温度パラメータ

    Returns:
        APIレスポンスとメタデータを含む辞書
    """
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_message,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=temperature,
            ),
        )
        return {
            "name": "Gemini",
            "icon": "🔵",
            "success": True,
            "content": response.text,
            "model": "gemini-2.0-flash",
            "role": role_name,
        }
    except Exception as e:
        return {
            "name": "Gemini",
            "icon": "🔵",
            "success": False,
            "content": f"エラー: {str(e)}",
            "model": "gemini-2.0-flash",
            "role": role_name,
        }


def call_chatgpt(
    api_key: str,
    system_prompt: str,
    user_message: str,
    role_name: str = "",
    temperature: float = 0.5,
) -> dict[str, Any]:
    """
    ChatGPT (OpenAI) のAPIを呼び出す関数

    Args:
        api_key: OpenAIのAPIキー
        system_prompt: システムプロンプト
        user_message: ユーザーメッセージ
        role_name: このAIの役割名
        temperature: 温度パラメータ

    Returns:
        APIレスポンスとメタデータを含む辞書
    """
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        return {
            "name": "ChatGPT",
            "icon": "🟢",
            "success": True,
            "content": response.choices[0].message.content,
            "model": "gpt-4o",
            "role": role_name,
        }
    except Exception as e:
        return {
            "name": "ChatGPT",
            "icon": "🟢",
            "success": False,
            "content": f"エラー: {str(e)}",
            "model": "gpt-4o",
            "role": role_name,
        }


def generate_image(
    api_key: str,
    prompt: str,
    quality: str = "medium",
    size: str = "1024x1024",
) -> dict[str, Any]:
    """
    OpenAIの画像生成APIを使用して画像を生成する関数

    Args:
        api_key: OpenAIのAPIキー
        prompt: 画像生成プロンプト
        quality: 品質 ("low", "medium", "high")
        size: 画像サイズ ("1024x1024", "1024x1536", "1536x1024")

    Returns:
        画像データとメタデータを含む辞書
    """
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            n=1,
            response_format="b64_json",
        )
        return {
            "success": True,
            "image_data": response.data[0].b64_json,
            "error": None,
            "revised_prompt": response.data[0].revised_prompt,
        }
    except Exception as e:
        return {
            "success": False,
            "image_data": None,
            "error": f"エラー: {str(e)}",
            "revised_prompt": None,
        }


def run_parallel(tasks: list[dict[str, Any]], progress_callback=None) -> list[dict[str, Any]]:
    """
    複数のタスクを並列実行する関数

    Args:
        tasks: {"fn": callable, "kwargs": dict, "name": str(任意)}のリスト
        progress_callback: タスク完了時に呼ばれるコールバック関数(任意)

    Returns:
        実行結果のリスト（インデックス付き）
    """
    results = [None] * len(tasks)

    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_index = {
            executor.submit(task["fn"], **task["kwargs"]): idx
            for idx, task in enumerate(tasks)
        }

        for future in as_completed(future_to_index):
            idx = future_to_index[future]
            try:
                results[idx] = future.result()
                if progress_callback:
                    name = tasks[idx].get("name", str(idx))
                    progress_callback(name)
            except Exception as e:
                results[idx] = {"error": str(e), "index": idx}

    return results


def run_sequential(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    複数のタスクを順序実行する関数

    Args:
        tasks: {"fn": callable, "kwargs": dict}のリスト

    Returns:
        実行結果のリスト
    """
    results = []

    for task in tasks:
        try:
            result = task["fn"](**task["kwargs"])
            results.append(result)
        except Exception as e:
            results.append({"error": str(e)})

    return results


def fetch_page_content(url: str) -> dict[str, Any]:
    """
    ウェブページのコンテンツを取得する関数

    Args:
        url: 取得するウェブページのURL

    Returns:
        ページのタイトル、メタディスクリプション、見出し、本文を含む辞書
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        title = ""
        if soup.title:
            title = soup.title.string or ""

        meta_description = ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        if meta_tag:
            meta_description = meta_tag.get("content", "")

        h1_tags = [h1.get_text() for h1 in soup.find_all("h1")]
        h2_tags = [h2.get_text() for h2 in soup.find_all("h2")]

        body_text = ""
        body = soup.find("body")
        if body:
            body_text = body.get_text()[:5000]

        return {
            "success": True,
            "title": title,
            "meta_description": meta_description,
            "h1_tags": h1_tags,
            "h2_tags": h2_tags,
            "body_text": body_text,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "title": "",
            "meta_description": "",
            "h1_tags": [],
            "h2_tags": [],
            "body_text": "",
            "error": f"エラー: {str(e)}",
        }


def search_competitors(
    api_key: str, search_engine_id: str, query: str, num_results: int = 5
) -> dict[str, Any]:
    """
    Google Custom Search APIを使用して検索する関数

    Args:
        api_key: Google APIキー
        search_engine_id: カスタム検索エンジンID
        query: 検索クエリ
        num_results: 取得する結果の数

    Returns:
        検索結果を含む辞書
    """
    if not api_key or not search_engine_id:
        return {
            "success": False,
            "results": [],
            "error": "APIキーまたは検索エンジンIDが未設定です",
        }

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "q": query,
            "key": api_key,
            "cx": search_engine_id,
            "num": num_results,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        results = []
        if "items" in data:
            for item in data["items"]:
                results.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                    }
                )

        return {
            "success": True,
            "results": results,
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "results": [],
            "error": f"エラー: {str(e)}",
        }
