"""
講義ノート要約AI - 共通ロジック

main.py (CLI) と app.py (Streamlit) の両方から使われる、
アップロード・要約生成・保存・キャッシュ管理などのコア機能をまとめたモジュール。
"""

from google import genai
import os
import json
import time
import hashlib
from datetime import datetime

MODEL_NAME = "gemini-3-flash-preview"
CACHE_FILE = ".upload_cache.json"
# Geminiのアップロード済みファイルは一定時間後にサーバー側で自動削除される。
# 正確な期限はAPI側の仕様変更もあり得るため、安全マージンを取って47時間で
# ローカルキャッシュ側を先に失効させる。
CACHE_TTL_SECONDS = 47 * 60 * 60

_client = None


def get_client() -> genai.Client:
    """Gemini APIクライアントを取得する(初回呼び出し時にだけ初期化)

    importされた瞬間にAPIキーチェックが走ると、Streamlit等GUI環境で
    予期しないタイミングで落ちてしまうため、実際に使う直前まで遅延させる。
    """
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "環境変数 GEMINI_API_KEY が設定されていません。"
                "Google AI Studio (https://aistudio.google.com/apikey) でキーを取得してください。"
            )
        _client = genai.Client(api_key=api_key)
    return _client


# --- 詳細度ごとの指示 ---
DETAIL_INSTRUCTIONS = {
    "simple": """
詳細度: 簡潔（試験直前の見直し用）
- 重要なポイントは3〜5個に絞り、1行で簡潔に書く（説明文は付けない）
- キーワードは特に重要なものだけ、最大5個まで
- まとめは1文だけ
- 細かい背景説明や具体例は省略する
""",
    "normal": """
詳細度: 標準
- 重要なポイントは5〜8個、各1〜2行で書く
- キーワードは登場した専門用語を一通り、簡潔な説明付きで
- まとめは2〜3文
""",
    "detailed": """
詳細度: 詳細（じっくり復習用）
- 重要なポイントは漏れなく拾い、各ポイントに「なぜそうなるか」「背景・補足」も1〜2文加える
- キーワードは関連する周辺知識も含めて説明する（その用語が出てくる文脈や、関連する別の用語があれば触れる）
- 内容に応じて、具体例や図表の説明があれば言葉で描写する
- まとめは4〜6文で、講義全体の流れがわかるように書く
""",
}

PROMPT_TEMPLATE = """
この画像（またはPDF）は講義のノートまたは黒板の写真です。以下の手順で処理してください。

1. 内容を正確に読み取る（手書き文字も含む）
2. 読み取った内容を、試験勉強に使える形に整理する
3. 以下のMarkdown形式で出力する

{detail_instruction}

## 講義タイトル（推測できれば。不明なら「タイトル不明」）

### 重要なポイント
- ポイント1
- ポイント2

### キーワード・専門用語
- 用語1: 説明
- 用語2: 説明

### まとめ
（詳細度の指示に従った文量で）

読み取れない部分があれば「(判読不能)」と記載してください。
余計な前置き（「はい、要約します」等）は不要です。Markdown本文のみ出力してください。
"""


def build_prompt(detail: str) -> str:
    """詳細度に応じたプロンプトを組み立てる"""
    return PROMPT_TEMPLATE.format(detail_instruction=DETAIL_INSTRUCTIONS[detail])


def _load_cache() -> dict:
    """ローカルのアップロードキャッシュを読み込む"""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    """ローカルのアップロードキャッシュを保存する"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _file_cache_key(file_path: str) -> str:
    """ファイルパス＋更新日時＋サイズからキャッシュキーを作る
    (中身が変わったファイルを誤って同一視しないため)
    """
    stat = os.stat(file_path)
    raw = f"{os.path.abspath(file_path)}:{stat.st_mtime}:{stat.st_size}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_or_upload_file(file_path: str):
    """キャッシュが有効ならアップロード済みファイルを再利用し、
    なければ新規にアップロードする
    """
    client = get_client()
    cache = _load_cache()
    key = _file_cache_key(file_path)
    entry = cache.get(key)

    if entry and (time.time() - entry["uploaded_at"] < CACHE_TTL_SECONDS):
        try:
            existing = client.files.get(name=entry["name"])
            print(f"  (キャッシュ済みファイルを再利用: {entry['name']})")
            return existing
        except Exception:
            print("  (キャッシュが無効だったため再アップロードします)")

    print("  (ファイルをアップロード中...)")
    uploaded_file = client.files.upload(file=file_path)
    cache[key] = {
        "name": uploaded_file.name,
        "uploaded_at": time.time(),
    }
    _save_cache(cache)
    return uploaded_file


def _describe_empty_response(response) -> str:
    """response.textがNoneだった場合に、原因を人間にわかる言葉にする"""
    if not response.candidates:
        return "AIから候補が1件も返ってきませんでした"

    candidate = response.candidates[0]
    finish_reason = str(getattr(candidate, "finish_reason", "")).split(".")[-1]

    reasons = {
        "SAFETY": "安全性フィルタによりブロックされました",
        "RECITATION": "著作権上の理由でブロックされました(元の文章に近すぎる可能性)",
        "MAX_TOKENS": "出力が長すぎて途中で打ち切られました(--detail simple を試すと改善する場合があります)",
        "OTHER": "不明な理由で生成が停止しました",
    }
    return reasons.get(finish_reason, f"原因不明(finish_reason={finish_reason})")


def summarize_note(file_path: str, detail: str = "normal") -> str:
    """講義ノートの画像/PDFを読み込んで要約を生成する"""
    client = get_client()
    prompt = build_prompt(detail)
    uploaded_file = get_or_upload_file(file_path)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, uploaded_file],
    )

    if response.text is None:
        reason = _describe_empty_response(response)
        raise RuntimeError(f"AIから有効な要約が得られませんでした: {reason}")

    return response.text


def save_summary(summary: str, source_file: str, detail: str, output_dir: str = "summaries") -> str:
    """要約をMarkdownファイルとして保存する"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.splitext(os.path.basename(source_file))[0]
    filepath = os.path.join(output_dir, f"{timestamp}_{base_name}_{detail}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary)
    return filepath