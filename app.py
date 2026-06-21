"""
講義ノート要約AI - Web UI版 (Streamlit)

使い方:
    1. pip install -r requirements.txt
    2. 環境変数 GEMINI_API_KEY にAPIキーを設定
    3. streamlit run app.py
"""

import os
import tempfile

import streamlit as st

from summarizer import summarize_note, save_summary

DETAIL_LABELS = {"simple": "簡潔", "normal": "標準", "detailed": "詳細"}

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

uploaded_file = st.file_uploader(
    "ノートの画像またはPDFをアップロード",
    type=["jpg", "jpeg", "png", "pdf"],
)

detail = st.radio(
    "要約の詳細度",
    options=["simple", "normal", "detailed"],
    format_func=lambda key: DETAIL_LABELS[key],
    index=1,
    horizontal=True,
)

if uploaded_file is not None:
    if uploaded_file.type.startswith("image"):
        st.image(uploaded_file, width=300)
    else:
        st.info(f"📄 {uploaded_file.name}")

    if st.button("要約する", type="primary"):
        # Gemini APIへの渡し方上、ファイルパスが必要なので一時ファイルに保存する
        suffix = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            with st.spinner("AIが解析中です..."):
                summary = summarize_note(tmp_path, detail)
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
        else:
            filepath = save_summary(summary, uploaded_file.name, detail)
            st.success(f"要約を生成しました（保存先: {filepath}）")
            st.markdown(summary)
            st.download_button(
                "Markdownをダウンロード",
                data=summary,
                file_name=os.path.basename(filepath),
                mime="text/markdown",
            )
        finally:
            os.remove(tmp_path)