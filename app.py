"""
講義ノート要約AI - Web UI版 (Streamlit)

使い方:
    1. pip install -r requirements.txt
    2. 環境変数 GEMINI_API_KEY にAPIキーを設定
    3. streamlit run app.py
"""

import os
import tempfile
import io

import streamlit as st

from summarizer import summarize_note, save_summary
from pdf_export import markdown_summary_to_pdf

DETAIL_LABELS = {"simple": "簡潔", "normal": "標準", "detailed": "詳細"}
TERM_LEVEL_LABELS = {"beginner": "初心者向け", "has_background": "前提知識あり"}

st.set_page_config(page_title="講義ノート要約AI", page_icon="📝")

st.title("📝 講義ノート要約AI")
st.caption("講義ノートや黒板の写真をアップロードすると、AIが試験勉強用に整理してくれます。")

if not os.environ.get("GEMINI_API_KEY"):
    st.error(
        "環境変数 `GEMINI_API_KEY` が設定されていません。\n\n"
        "[Google AI Studio](https://aistudio.google.com/apikey) でキーを取得し、"
        "アプリを起動する前に `export GEMINI_API_KEY=\"your-key\"` のように設定してください。"
    )
    st.stop()

uploaded_files = st.file_uploader(
    "ノートの画像またはPDFをアップロード(複数選択可)",
    type=["jpg", "jpeg", "png", "pdf"],
    accept_multiple_files=True,
    help="複数選ぶと、選んだ順に同じ講義のページとして1つの要約にまとめます。",
)

col_detail, col_term = st.columns(2)
with col_detail:
    detail = st.radio(
        "要約の詳細度",
        options=["simple", "normal", "detailed"],
        format_func=lambda key: DETAIL_LABELS[key],
        index=1,
        horizontal=True,
    )
with col_term:
    term_level = st.radio(
        "用語説明の粒度",
        options=["beginner", "has_background"],
        format_func=lambda key: TERM_LEVEL_LABELS[key],
        index=0,
        horizontal=True,
    )

if uploaded_files:
    st.caption(f"{len(uploaded_files)}件のファイルを、表示順に1つの講義として要約します。")
    for f in uploaded_files:
        if f.type.startswith("image"):
            st.image(f, width=300, caption=f.name)
        else:
            st.info(f"📄 {f.name}")

    if st.button("要約する", type="primary"):
        # Gemini APIへの渡し方上、ファイルパスが必要なので一時ファイルに保存する
        tmp_paths = []
        try:
            for f in uploaded_files:
                suffix = os.path.splitext(f.name)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(f.getvalue())
                    tmp_paths.append(tmp.name)

            with st.spinner("AIが解析中です..."):
                summary = summarize_note(tmp_paths, detail, term_level)
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
        else:
            source_names = [f.name for f in uploaded_files]
            filepath = save_summary(summary, source_names, detail, term_level)
            st.success(f"要約を生成しました（保存先: {filepath}）")
            st.markdown(summary)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "Markdownをダウンロード",
                    data=summary,
                    file_name=os.path.basename(filepath),
                    mime="text/markdown",
                )
            with col2:
                try:
                    pdf_buffer = io.BytesIO()
                    markdown_summary_to_pdf(summary, pdf_buffer)
                    pdf_name = os.path.splitext(os.path.basename(filepath))[0] + ".pdf"
                    st.download_button(
                        "PDFをダウンロード",
                        data=pdf_buffer.getvalue(),
                        file_name=pdf_name,
                        mime="application/pdf",
                    )
                except RuntimeError as e:
                    st.warning(f"PDF生成をスキップしました: {e}")
        finally:
            for path in tmp_paths:
                if os.path.exists(path):
                    os.remove(path)
