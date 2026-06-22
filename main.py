"""
講義ノート要約AI - CLI版

使い方:
    1. pip install -r requirements.txt
    2. 環境変数 GEMINI_API_KEY にAPIキーを設定
       (Mac/Linux: export GEMINI_API_KEY="your-key-here")
       (Windows:   set GEMINI_API_KEY=your-key-here)
    3. python main.py <画像またはPDFファイルパス> [--detail simple|normal|detailed]

例:
    python main.py photo.jpg
    python main.py sample.pdf --detail detailed
"""

import argparse
import os
import sys

from summarizer import summarize_note, save_summary, save_summary_pdf


def parse_args():
    parser = argparse.ArgumentParser(description="講義ノート画像/PDFをAIで要約する")
    parser.add_argument("file_path", help="画像またはPDFファイルのパス")
    parser.add_argument(
        "--detail",
        choices=["simple", "normal", "detailed"],
        default="normal",
        help="要約の詳細度 (デフォルト: normal)",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Markdownに加えて、整形済みPDFも出力する",
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
    print(f"\n要約を保存しました: {filepath}")

    if args.pdf:
        pdf_path = save_summary_pdf(summary, args.file_path, args.detail)
        print(f"PDFを保存しました: {pdf_path}")

    print()
    print("=" * 50)
    print(summary)
    print("=" * 50)


if __name__ == "__main__":
    main()