"""
要約Markdownを整形されたPDFに変換するモジュール
"""

import os
import re
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- 日本語フォントの自動検出 ---
# 環境によってインストール場所が異なるため、よくあるパスを順番に探す。
# 見つからない場合は PDF_FONT_PATH 環境変数で明示的に指定できる。
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",     # Debian/Ubuntu (IPAフォント)
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",        # Debian/Ubuntu (IPAフォント 別名)
    "/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf",  # Debian/Ubuntu (Takaoフォント)
    "/Library/Fonts/Arial Unicode.ttf",                          # macOS
    "C:/Windows/Fonts/YuGothM.ttc",                              # Windows 10/11
    "C:/Windows/Fonts/meiryo.ttc",                               # Windows
]
_FONT_NAME = "JapaneseFont"
_font_registered = False


def _ensure_japanese_font() -> str:
    """日本語フォントを検出して登録する。見つからなければ分かりやすいエラーを出す。"""
    global _font_registered
    if _font_registered:
        return _FONT_NAME

    custom_path = os.environ.get("PDF_FONT_PATH")
    candidates = ([custom_path] if custom_path else []) + _FONT_CANDIDATES

    for path in candidates:
        if path and os.path.exists(path):
            pdfmetrics.registerFont(TTFont(_FONT_NAME, path))
            # 太字フォントは別途用意していないため、同じフォントを太字としても登録する
            # (<b>タグを使っても視覚的な太さは変わらないが、エラーにはならない)
            pdfmetrics.registerFontFamily(
                _FONT_NAME, normal=_FONT_NAME, bold=_FONT_NAME,
                italic=_FONT_NAME, boldItalic=_FONT_NAME,
            )
            _font_registered = True
            return _FONT_NAME

    raise RuntimeError(
        "日本語フォントが見つかりませんでした。以下のいずれかを行ってください。\n"
        "  1) Linux: sudo apt install fonts-ipafont-gothic\n"
        "  2) 環境変数 PDF_FONT_PATH に使用したいフォントファイル(.ttf)のパスを設定する"
    )


def _inline_markdown_to_xml(text: str) -> str:
    """**太字** をreportlabの<b>タグに変換する(簡易対応)"""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text


def _build_styles(font_name: str):
    styles = getSampleStyleSheet()
    return {
        "JTitle": ParagraphStyle(
            "JTitle", parent=styles["Title"], fontName=font_name,
            fontSize=18, leading=24, spaceAfter=14, textColor=HexColor("#111111"),
        ),
        "JHeading2": ParagraphStyle(
            "JHeading2", parent=styles["Heading2"], fontName=font_name,
            fontSize=13, leading=18, spaceBefore=14, spaceAfter=8,
            textColor=HexColor("#1f4e79"),
        ),
        "JBody": ParagraphStyle(
            "JBody", parent=styles["Normal"], fontName=font_name,
            fontSize=10.5, leading=16, alignment=TA_LEFT,
        ),
        "JBullet": ParagraphStyle(
            "JBullet", parent=styles["Normal"], fontName=font_name,
            fontSize=10.5, leading=16,
        ),
    }


def markdown_summary_to_pdf(markdown_text: str, output) -> None:
    """要約Markdown文字列を読みやすいPDFに変換する

    output: ファイルパス(str)、またはBytesIOなどの書き込み可能なバッファ
    """
    font_name = _ensure_japanese_font()
    styles = _build_styles(font_name)
    doc = SimpleDocTemplate(
        output, pagesize=A4,
        topMargin=20 * mm, bottomMargin=20 * mm,
        leftMargin=20 * mm, rightMargin=20 * mm,
    )
    story = []
    bullet_buffer = []

    def flush_bullets():
        nonlocal bullet_buffer
        if bullet_buffer:
            items = [
                ListItem(Paragraph(_inline_markdown_to_xml(b), styles["JBullet"]),
                         bulletColor=HexColor("#1f4e79"))
                for b in bullet_buffer
            ]
            story.append(ListFlowable(
                items, bulletType="bullet", leftIndent=14,
                bulletFontName=font_name,
            ))
            story.append(Spacer(1, 6))
            bullet_buffer = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            flush_bullets()
            continue

        if line.startswith("## "):
            flush_bullets()
            story.append(Paragraph(_inline_markdown_to_xml(line[3:]), styles["JTitle"]))
        elif line.startswith("### "):
            flush_bullets()
            story.append(Paragraph(_inline_markdown_to_xml(line[4:]), styles["JHeading2"]))
        elif line.startswith("- "):
            bullet_buffer.append(line[2:])
        else:
            flush_bullets()
            story.append(Paragraph(_inline_markdown_to_xml(line), styles["JBody"]))
            story.append(Spacer(1, 4))

    flush_bullets()
    doc.build(story)
