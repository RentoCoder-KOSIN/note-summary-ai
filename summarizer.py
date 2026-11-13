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

from pdf_export import markdown_summary_to_pdf

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
        # Gemini 3 preview models are exposed through the v1beta
        # generateContent endpoint. The SDK may otherwise select v1.
        _client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )
    return _client


# --- 詳細度ごとの指示 ---
DETAIL_INSTRUCTIONS = {
    "simple": """
詳細度: 簡潔（試験直前の見直し用）
- ページごとの重要事項を確認したうえで、重複をまとめてトピックごとに1〜2個に絞り、1行で簡潔に書く（説明文は付けない）
- キーワードは特に重要なものだけ、トピックごとに最大3個程度
- 細かい背景説明や具体例は省略する。ただし資料中の数値・単位・公式・結論は省かず残す
""",
    "normal": """
詳細度: 標準
- 資料のトピック（スライド1〜3枚程度のまとまり）ごとに、重要なポイントを2〜4個、各1〜2行で書く
- ポイントの総数に上限はない。資料が長ければ、その分多くなってよい
- 各ページを確認し、数値・単位・公式・分類表は省略せず、値ごと書く
- 例題・問題が載っていれば、問題文の要点と解答（式と答え）を書く
- キーワードは登場した専門用語・略語をすべて、簡潔な説明付きで書く（略語は正式名称を併記）
""",
    "detailed": """
詳細度: 詳細（じっくり復習用）
- 資料の全スライド・全ページを対象に、重要なポイントを漏れなく拾い、各ポイントに「なぜそうなるか」「背景・補足」も1〜2文加える。ページ後半も前半と同じ密度で扱う
- 数値・単位・公式・分類表は、すべて項目ごとに再現する
- 例題・問題が載っていれば、問題文、解答（途中式を含む）、答えを書く
- キーワードは登場した専門用語・略語をすべて拾い、関連する周辺知識も含めて説明する（略語は正式名称を併記。その用語が出てくる文脈や、関連する別の用語があれば触れる）
- 図表・図解があれば、何が描かれているか、どこがポイントかを言葉で描写する
""",
}

# --- 用語説明の粒度(読者の前提知識レベル) ---
TERM_LEVEL_INSTRUCTIONS = {
    "beginner": """
用語粒度: 初心者向け
- 専門用語は、その分野を全く知らない人にもわかるように噛み砕いて説明する
- 抽象的な言葉を使う場合は、可能であれば具体例を1つ添える
""",
    "has_background": """
用語粒度: 前提知識あり
- 用語の意味そのものの説明は最小限にとどめ、「その用語が講義内でどう使われたか」という文脈情報を優先する
- 既に知っていて当然の基礎用語は、説明を省略してよい
""",
}

PROMPT_TEMPLATE = """
あなたは、大学の講義ノートを試験勉強用に整理するアシスタントです。
添付されたのは、講義の資料（ノート・黒板の写真・スライドのPDF）です（全{file_count}件）。
複数ある場合、同じ講義の続きのこともあれば、別々の回・別々のテーマのこともあります。
無理に1つのテーマへ統合せず、内容のまとまり（トピック）ごとに整理してください。

## 手順
1. すべてのファイルの内容を正確に読み取る（手書き文字も含む）
2. ファイル間で重複している内容だけを1つにまとめる（各ファイルの内容を削って短くしない）
3. 試験勉強に使える形に整理し、下の「出力形式」に従って出力する

## 守ること
- ノートに書かれていない内容を、推測や一般知識で付け足さない。補足が必要なときだけ「（補足）」と明記して書く
- 読み取れない部分は「(判読不能)」と書き、推測で埋めない
- 図・表・数式は、意味が伝わるように言葉や表記で再現する。数式は可能なら LaTeX のインライン形式 `$...$` または独立行 `$$...$$` で記す
- 数値・単位・公式・表の中身・略語・固有名詞は省略せず、値まで書く（例:「カテゴリ5eは最大100MHz」のように具体値を残す）
- 例題・問題が載っていれば解いて解答を付ける。解答が資料に書かれていない場合は「（解答例）」と明記する
- 資料が長くても要約を短くまとめすぎない。すべてのファイル・ページを均等に拾い、後半を手薄にしない。出力前にページごとに数値・公式・表・例題の転記漏れがないか照合する

## 重要なポイントを選ぶ基準
以下に当たる情報を優先的に拾ってください。単なる言い換えや装飾的な発言は拾わないこと。
1. 定義・概念の説明
2. 因果関係・条件分岐（「〜なら〜になる」等）
3. 比較・対比構造
4. 手順・アルゴリズムのステップ
5. 試験で問われやすそうな具体的な数値・固有名詞・用語

{detail_instruction}

{term_level_instruction}

## 出力形式
次の見出し構造のまま、Markdown本文のみを出力してください。
前置き（「はい、要約します」等）や、全体を囲むコードブロックは不要です。

## （講義タイトルだけを書く。複数テーマなら「／」でつなぐ。推測できなければ「タイトル不明」）

### 重要なポイント
トピックごとに、トピック名を太字の行にして、その下に箇条書きを置く。

**トピック名1**
- ポイント1
- ポイント2

**トピック名2**
- ポイント1

### キーワード・専門用語
- 用語1: 説明
- 用語2: 説明
"""


def build_prompt(detail: str, term_level: str = "beginner", file_count: int = 1) -> str:
    """詳細度・用語粒度・ファイル数に応じたプロンプトを組み立てる"""
    return PROMPT_TEMPLATE.format(
        file_count=file_count,
        detail_instruction=DETAIL_INSTRUCTIONS[detail],
        term_level_instruction=TERM_LEVEL_INSTRUCTIONS[term_level],
    )


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


def summarize_note(
    file_paths: str | list[str],
    detail: str = "normal",
    term_level: str = "beginner",
) -> str:
    """講義ノートの画像/PDFを読み込んで要約を生成する

    file_paths は1件(str)でも複数件(list)でもよい。
    複数の場合は渡した順に同じ講義の続きとして読み、1つの要約に統合する。
    """
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    if not file_paths:
        raise ValueError("要約するファイルが指定されていません")

    client = get_client()
    prompt = build_prompt(detail, term_level, file_count=len(file_paths))

    contents = [prompt]
    for i, path in enumerate(file_paths, start=1):
        uploaded_file = get_or_upload_file(path)
        if len(file_paths) > 1:
            contents.append(f"--- ファイル {i} / {len(file_paths)} ---")
        contents.append(uploaded_file)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
    )

    if response.text is None:
        reason = _describe_empty_response(response)
        raise RuntimeError(f"AIから有効な要約が得られませんでした: {reason}")

    return response.text


def _source_base_name(source_file: str | list[str]) -> str:
    """保存ファイル名に使う元ファイル名を作る(複数なら「先頭_他N件」)"""
    if isinstance(source_file, str):
        source_file = [source_file]
    first = os.path.splitext(os.path.basename(source_file[0]))[0]
    if len(source_file) > 1:
        return f"{first}_他{len(source_file) - 1}件"
    return first


def save_summary(
    summary: str,
    source_file: str | list[str],
    detail: str,
    term_level: str = "beginner",
    output_dir: str = "summaries",
) -> str:
    """要約をMarkdownファイルとして保存する"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = _source_base_name(source_file)
    filepath = os.path.join(output_dir, f"{timestamp}_{base_name}_{detail}_{term_level}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary)
    return filepath


def save_summary_pdf(
    summary: str,
    source_file: str | list[str],
    detail: str,
    term_level: str = "beginner",
    output_dir: str = "summaries",
) -> str:
    """要約を整形済みPDFとして保存する"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = _source_base_name(source_file)
    filepath = os.path.join(output_dir, f"{timestamp}_{base_name}_{detail}_{term_level}.pdf")
    markdown_summary_to_pdf(summary, filepath)
    return filepath
