import os
import requests
import io
import streamlit as st
from PIL import Image

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="Dandelion vs Grass", layout="centered")
st.title("🌿 Dandelion vs Grass — Demo")

tab1, tab2 = st.tabs(["Single Image", "Batch (URLs)"])

with tab1:
    f = st.file_uploader("Upload an image", type=["jpg","jpeg","png"])
    if f and st.button("Predict"):
        files = {"file": (f.name, f.getvalue(), f"type/{f.type}")}
        r = requests.post(f"{API_BASE_URL}/predict", files=files, timeout=60)
        st.image(Image.open(io.BytesIO(f.getvalue())).convert("RGB"), width=320)
        st.json(r.json())

with tab2:
    urls = st.text_area("One URL per line", height=200, placeholder="https://...")
    if st.button("Predict URLs"):
        for u in urls.splitlines():
            u = u.strip()
            if not u:
                continue
            try:
                img_bytes = requests.get(u, timeout=20).content
                files = {"file": ("img.jpg", img_bytes, "image/jpeg")}
                r = requests.post(f"{API_BASE_URL}/predict", files=files, timeout=60)
                st.image(Image.open(io.BytesIO(img_bytes)).convert("RGB"), width=200, caption=u)
                st.json(r.json())
            except Exception as e:
                st.error(f"{u} -> {e}")
