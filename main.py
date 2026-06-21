"""
講義ノート要約AI - MVP版 (google-genai SDK)

使い方:
    1. pip install google-genai
    2. 環境変数 GEMINI_API_KEY にAPIキーを設定
       (Mac/Linux: export GEMINI_API_KEY="your-key-here")
       (Windows:   set GEMINI_API_KEY=your-key-here)
    3. python main.py <画像またはPDFファイルパス> [--detail simple|normal|detailed]

例:
    python main.py photo.jpg
    python main.py sample.pdf --detail detailed
    python main.py sample.pdf --detail simple
"""

from google import genai
import argparse
import sys
import os
from datetime import datetime

# --- 初期設定 ---
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("エラー: 環境変数 GEMINI_API_KEY が設定されていません。")
    print("Google AI Studio (https://aistudio.google.com/apikey) でキーを取得してください。")
    sys.exit(1)

client = genai.Client(api_key=API_KEY)
MODEL_NAME = "gemini-3-flash-preview"

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


def summarize_note(file_path: str, detail: str = "normal") -> str:
    """講義ノートの画像/PDFを読み込んで要約を生成する"""
    prompt = build_prompt(detail)
    uploaded_file = client.files.upload(file=file_path)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt, uploaded_file],
    )
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


def parse_args():
    parser = argparse.ArgumentParser(description="講義ノート画像/PDFをAIで要約する")
    parser.add_argument("file_path", help="画像またはPDFファイルのパス")
    parser.add_argument(
        "--detail",
        choices=["simple", "normal", "detailed"],
        default="normal",
        help="要約の詳細度 (デフォルト: normal)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.file_path):
        print(f"エラー: ファイルが見つかりません: {args.file_path}")
        sys.exit(1)

    print(f"ファイルを解析中...（詳細度: {args.detail}）")
    try:
        summary = summarize_note(args.file_path, args.detail)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

    filepath = save_summary(summary, args.file_path, args.detail)

    print(f"\n要約を保存しました: {filepath}\n")
    print("=" * 50)
    print(summary)
    print("=" * 50)


if __name__ == "__main__":
    main()
