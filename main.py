"""
講義ノート要約AI - MVP版 (google-genai SDK)

使い方:
    1. pip install google-genai
    2. 環境変数 GEMINI_API_KEY にAPIキーを設定
       (Mac/Linux: export GEMINI_API_KEY="your-key-here")
       (Windows:   set GEMINI_API_KEY=your-key-here)
    3. python main.py <画像またはPDFファイルパス>

例:
    python main.py photo.jpg
    python main.py sample.pdf
"""

from google import genai
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

SUMMARY_PROMPT = """
この画像（またはPDF）は講義のノートまたは黒板の写真です。以下の手順で処理してください。

1. 内容を正確に読み取る（手書き文字も含む）
2. 読み取った内容を、試験勉強に使える形に整理する
3. 以下のMarkdown形式で出力する

## 講義タイトル（推測できれば。不明なら「タイトル不明」）

### 重要なポイント
- ポイント1
- ポイント2

### キーワード・専門用語
- 用語1: 説明
- 用語2: 説明

### まとめ
（2〜3文で全体を要約）

読み取れない部分があれば「(判読不能)」と記載してください。
余計な前置き（「はい、要約します」等）は不要です。Markdown本文のみ出力してください。
"""


def summarize_note(file_path: str) -> str:
    """講義ノートの画像/PDFを読み込んで要約を生成する"""
    uploaded_file = client.files.upload(file=file_path)
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[SUMMARY_PROMPT, uploaded_file],
    )
    return response.text


def save_summary(summary: str, source_file: str, output_dir: str = "summaries") -> str:
    """要約をMarkdownファイルとして保存する"""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = os.path.splitext(os.path.basename(source_file))[0]
    filepath = os.path.join(output_dir, f"{timestamp}_{base_name}.md")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(summary)
    return filepath


def main():
    if len(sys.argv) < 2:
        print("使い方: python main.py <画像またはPDFファイルパス>")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"エラー: ファイルが見つかりません: {file_path}")
        sys.exit(1)

    print("ファイルを解析中...")
    try:
        summary = summarize_note(file_path)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

    filepath = save_summary(summary, file_path)

    print(f"\n要約を保存しました: {filepath}\n")
    print("=" * 50)
    print(summary)
    print("=" * 50)


if __name__ == "__main__":
    main()
