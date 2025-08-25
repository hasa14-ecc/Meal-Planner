import streamlit as st
import json
import requests
import time
from typing import List, Dict, Any
from nutrition_db import food_database
import logging
import os
from agent import get_encryption_key, encrypt_data, decrypt_data, MealPlannerAgent
from prompts import general_food_prompt, negative_prompt
import random

logger = logging.getLogger(__name__)

GROQ_API_URL = st.secrets.get("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")

def call_chat_api(prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    api_key_enc = st.secrets.get("ENCRYPTED_GROQ_API_KEY")
    if not api_key_enc:
        logger.error("ENCRYPTED_GROQ_API_KEY tidak ditemukan di st.secrets.")
        return "(Error) Konfigurasi API key tidak ditemukan. Periksa .streamlit/secrets.toml."
    
    api_key = decrypt_data(api_key_enc)
    if not api_key:
        logger.error("Gagal mendekripsi API key. Memeriksa encryption_key.key.")
        # Tambahan logging untuk debugging
        if not os.path.exists("encryption_key.key"):
            logger.error("File encryption_key.key tidak ditemukan di direktori.")
        else:
            logger.error("File encryption_key.key ditemukan, tetapi dekripsi gagal. Pastikan kunci cocok dengan ENCRYPTED_GROQ_API_KEY.")
        return (
            "(Error) Gagal mendekripsi API key. Pastikan file encryption_key.key valid dan cocok dengan kunci di secrets.toml."
        )
    
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except requests.RequestException as e:
        logger.error(f"API call failed: {e}")
        return f"(Error) Gagal memanggil API: {str(e)}"

def save_chat_history_to_file(history: List[Dict[str, Any]], filename: str = "chat_history.json") -> tuple[bool, str]:
    try:
        encrypted_history = encrypt_data(json.dumps(history, ensure_ascii=False))
        with open(filename, "w", encoding="utf-8") as f:
            f.write(encrypted_history)
        return True, filename
    except Exception as e:
        logger.error(f"Gagal simpan history: {e}")
        return False, str(e)

def load_chat_history_from_file(filename: str = "chat_history.json") -> List[Dict[str, Any]]:
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            encrypted = f.read()
            decrypted = decrypt_data(encrypted)
            if decrypted:
                return json.loads(decrypted)
            else:
                logger.error("Gagal mendekripsi chat history.")
                return []
    return []

def format_meal_plan(plan: Dict[str, Any], goal: Dict[str, Any], prompt: str) -> str:
    """
    Format rencana makan dengan respons dinamis berdasarkan prompt.
    """
    target_kcal = goal.get("target_kcal_per_day", 1)
    target_protein = goal.get("min_protein_per_day", 1)
    prompt_l = prompt.lower()

    # Tentukan konteks berdasarkan prompt
    context = "diet sehat"
    if "bulking" in prompt_l or "menambah berat" in prompt_l:
        context = "bulking"
    elif "diet" in prompt_l or "menurunkan berat" in prompt_l:
        context = "cutting"
    elif "tinggi protein" in prompt_l:
        context = "tinggi protein"

    # Variasi pembuka berdasarkan konteks
    openings = {
        "bulking": [
            "Rencana makan untuk mendukung bulking dan peningkatan massa otot!",
            "Menu untuk menambah berat badan dengan kalori dan protein tinggi!",
            "Rencana nutrisi untuk mendukung tujuan bulking Anda!"
        ],
        "cutting": [
            "Rencana makan untuk membantu diet dan menurunkan berat badan!",
            "Menu rendah kalori untuk mendukung tujuan cutting Anda!",
            "Rencana nutrisi untuk diet sehat dan terkendali!"
        ],
        "tinggi protein": [
            "Rencana makan tinggi protein untuk mendukung otot dan performa!",
            "Menu kaya protein untuk tujuan nutrisi Anda!",
            "Rencana makan untuk asupan protein maksimal!"
        ],
        "diet sehat": [
            "Rencana makan seimbang untuk gaya hidup sehat!",
            "Menu harian untuk nutrisi optimal dan kesehatan!",
            "Rencana makan untuk mendukung pola makan sehat!"
        ]
    }
    output = [f"### {random.choice(openings[context])}"]
    output.append(f"**Target**: {target_kcal:.0f} kkal/hari, {target_protein:.0f} g protein/hari\n")

    # Tabel statistik
    output.append("#### Ringkasan Nutrisi Harian")
    output.append("| Hari | Kalori (kkal) | Protein (g) | Karbo (g) | Lemak (g) | % Target Kalori | % Target Protein |")
    output.append("|------|---------------|-------------|-----------|-----------|-----------------|------------------|")
    for day, info in plan.items():
        kcal = info.get("total_kalori", 0)
        prot = info.get("total_protein", 0.0)
        karbo = info.get("total_karbo", 0.0)
        lemak = info.get("total_lemak", 0.0)
        pct_kcal = (kcal / target_kcal * 100) if target_kcal != 0 else 0
        pct_protein = (prot / target_protein * 100) if target_protein != 0 else 0
        output.append(f"| {day} | {kcal:.0f} | {prot:.1f} | {karbo:.1f} | {lemak:.1f} | {pct_kcal:.1f}% | {pct_protein:.1f}% |")

    # Detail menu
    output.append("\n#### Detail Menu")
    for day, info in plan.items():
        output.append(f"##### Hari {day}")
        output.append(f"**Total**: {info.get('total_kalori', 0):.0f} kkal, {info.get('total_protein', 0):.1f} g protein, "
                      f"{info.get('total_karbo', 0):.1f} g karbo, {info.get('total_lemak', 0):.1f} g lemak")
        for meal, items in info.get("meals", {}).items():
            output.append(f"\n**{meal.capitalize()}:**")
            if not items:
                output.append("- Tidak ada makanan yang ditemukan untuk waktu makan ini.")
                continue
            for item in items:
                name = item.get("name", "unknown")
                kcal = item.get("kalori", 0)
                prot = item.get("protein", 0.0)
                karbo = item.get("karbo", 0.0)
                lemak = item.get("lemak", 0.0)
                found = item.get("found", True)
                status = "✅" if found else "⚠️ (tidak ditemukan)"
                output.append(f"- {name}: {kcal:.0f} kkal, {prot:.1f} g protein, {karbo:.1f} g karbo, {lemak:.1f} g lemak {status}")
        output.append("")

    # Variasi RAG berdasarkan konteks
    reasoning_variations = {
        "bulking": [
            "Rencana ini dirancang untuk surplus kalori guna mendukung pertumbuhan otot dengan sumber protein berkualitas.",
            "Menu ini dioptimalkan untuk asupan kalori dan protein tinggi, sesuai kebutuhan bulking.",
            "Pilihan makanan ini memastikan variasi nutrisi untuk mendukung latihan berat dan pemulihan otot."
        ],
        "cutting": [
            "Rencana ini dibuat untuk defisit kalori ringan sambil menjaga asupan protein untuk mempertahankan otot.",
            "Menu ini fokus pada makanan rendah kalori namun kaya nutrisi untuk mendukung penurunan berat badan.",
            "Pilihan makanan ini membantu menjaga keseimbangan nutrisi dengan kalori terkendali."
        ],
        "tinggi protein": [
            "Rencana ini memaksimalkan asupan protein untuk mendukung pertumbuhan otot dan pemulihan.",
            "Menu ini memastikan protein tinggi dari berbagai sumber untuk performa optimal.",
            "Pilihan makanan ini kaya protein untuk mendukung tujuan nutrisi Anda."
        ],
        "diet sehat": [
            "Rencana ini dirancang untuk keseimbangan nutrisi dengan kalori dan protein yang sesuai.",
            "Menu ini mendukung gaya hidup sehat dengan variasi makanan bergizi.",
            "Pilihan makanan ini memastikan asupan nutrisi lengkap untuk kesehatan jangka panjang."
        ]
    }
    advice_variations = {
        "bulking": [
            "Tambahkan camilan tinggi kalori seperti kacang almond atau protein shake.",
            "Konsumsi makanan kaya karbohidrat kompleks seperti nasi merah atau kentang.",
            "Pastikan asupan kalori harian melebihi kebutuhan untuk surplus."
        ],
        "cutting": [
            "Ganti karbohidrat sederhana dengan sayuran rendah kalori untuk defisit.",
            "Pilih sumber protein rendah lemak seperti dada ayam atau ikan kukus.",
            "Kurangi porsi karbohidrat dan tingkatkan sayuran hijau."
        ],
        "tinggi protein": [
            "Tambahkan sumber protein seperti telur atau ikan pada setiap waktu makan.",
            "Gunakan protein shake sebagai camilan untuk memenuhi target protein.",
            "Pilih makanan kaya protein seperti ayam, ikan, atau tahu."
        ],
        "diet sehat": [
            "Variasikan warna sayuran untuk asupan vitamin dan mineral yang lengkap.",
            "Konsumsi lemak sehat seperti alpukat atau minyak zaitun secukupnya.",
            "Pastikan hidrasi dengan minum air putih minimal 2 liter per hari."
        ]
    }
    guidance_variations = {
        "bulking": [
            "Pantau kenaikan berat badan mingguan (target 0.5-1 kg).",
            "Konsumsi makanan setiap 3-4 jam untuk menjaga surplus kalori.",
            "Fokus pada latihan beban untuk memaksimalkan pertumbuhan otot."
        ],
        "cutting": [
            "Pantau berat badan mingguan untuk memastikan defisit kalori terjaga.",
            "Konsumsi makanan tinggi serat untuk menjaga rasa kenyang.",
            "Lakukan aktivitas kardio ringan untuk mendukung penurunan berat."
        ],
        "tinggi protein": [
            "Distribusikan asupan protein merata di setiap waktu makan.",
            "Konsumsi protein dalam 1-2 jam setelah latihan untuk pemulihan.",
            "Pantau asupan protein harian untuk memastikan target terpenuhi."
        ],
        "diet sehat": [
            "Jaga konsistensi waktu makan untuk metabolisme optimal.",
            "Kurangi makanan olahan dan fokus pada bahan segar.",
            "Pantau porsi untuk menjaga keseimbangan kalori dan nutrisi."
        ]
    }
    output.append(f"**Reasoning**: {random.choice(reasoning_variations[context])}")
    output.append(f"**Advice**: {random.choice(advice_variations[context])}")
    output.append(f"**Guidance**: {random.choice(guidance_variations[context])}")
    output.append("**Disclaimer**: Ini bukan saran medis profesional. Konsultasikan dengan dokter atau ahli gizi.")

    return "\n".join(output)

def format_general_response(response: str) -> str:
    """Format respons umum dengan disclaimer."""
    return f"{response}\n\n**Disclaimer**: Ini bukan saran medis profesional. Konsultasikan ahli jika diperlukan."

def app():
    st.markdown("""
    <style>
    /* Background utama dengan warna abu-abu gelap */
    .stApp {
        background-color: #1A202C;
        font-family: 'Inter', sans-serif;
        color: #E2E8F0;
    }
    /* Header aplikasi */
    .chat-header {
        background: linear-gradient(90deg, #2D3748, #1A202C 80%);
        color: #FFFFFF;
        padding: 18px 28px 12px 28px;
        border-radius: 12px;
        margin-bottom: 18px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
        font-size: 22px;
        font-weight: 700;
        letter-spacing: 0.5px;
        display: flex;
        align-items: center;
        gap: 16px;
    }
    /* Chat bubble untuk user */
    .chat-bubble-user {
        background: #4A5568;
        color: #E2E8F0;
        border-radius: 16px 16px 4px 16px;
        padding: 10px 16px;
        margin: 6px 0 6px 40px;
        max-width: 80%;
        font-size: 16px;
        align-self: flex-end;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
    }
    /* Chat bubble untuk assistant */
    .chat-bubble-assistant {
        background: #2A2E3B;
        color: #E2E8F0;
        border-radius: 16px 16px 16px 4px;
        padding: 10px 16px;
        margin: 6px 40px 6px 0;
        max-width: 80%;
        font-size: 16px;
        border: 1px solid #4A5568;
        align-self: flex-start;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
    }
    /* Disclaimer */
    .disclaimer {
        color: #E53E3E;
        font-style: italic;
        font-size: 14px;
    }
    /* Styling untuk tombol */
    .stButton>button {
        background-color: #2A9D8F;
        color: #FFFFFF;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 500;
        transition: background-color 0.3s;
    }
    .stButton>button:hover {
        background-color: #1C6B61;
    }
    /* Styling untuk selectbox */
    .stSelectbox>div>div {
        border-radius: 8px;
        border: 1px solid #4A5568;
        background-color: #2D3748;
        color: #FFFFFF;
    }
    /* Styling untuk chat input */
    .stChatInput>div>input {
        border-radius: 8px;
        border: 1px solid #4A5568;
        background-color: #2D3748;
        color: #FFFFFF;
        padding: 10px;
    }
    /* Styling untuk sidebar tips */
    .sidebar-tips {
        background: #2D3748;
        padding: 12px 16px;
        border-radius: 10px;
        color: #E2E8F0;
        font-size: 15px;
        margin-bottom: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="chat-header">🤖 Chat Makanan AI (Luas & Interaktif)</div>', unsafe_allow_html=True)
    st.write(
        "Chat ini bisa membahas <b>segala hal tentang makanan secara luas</b>: resep, sejarah, fakta nutrisi, budaya makanan, tips memasak, dll.<br>"
        "Tanyakan apa saja terkait makanan, seperti 'Sejarah pizza' atau 'Resep nasi goreng'. Jika ingin meal plan, sebutkan 'rencana makan' atau 'diet'.<br>"
        "Jawaban bisa dalam format <b>RAG (Reasoning, Advice, Guidance)</b> jika relevan.",
        unsafe_allow_html=True
    )
    st.markdown("<p class='disclaimer'>Disclaimer: Ini bukan pengganti saran medis profesional.</p>", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-tips">
            <b>Tips Chat:</b><br>
            • Tanyakan apa saja tentang makanan, misal:<br>
            &nbsp; - 'Sejarah sushi'<br>
            &nbsp; - 'Resep ayam bakar'<br>
            &nbsp; - 'Manfaat nutrisi alpukat'<br>
            &nbsp; - 'Rencana makan untuk bulking'<br>
            • AI akan memberikan jawaban luas atau rencana makan sesuai konteks.<br>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = load_chat_history_from_file()

    model = st.selectbox("Pilih model (opsional)", ["llama-3.3-70b-versatile", "demo-echo"])

    for msg in st.session_state.chat_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            st.markdown(f'<div class="chat-bubble-user">{content}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-bubble-assistant">{content}</div>', unsafe_allow_html=True)

    prompt = st.chat_input("Tanyakan tentang makanan, resep, sejarah, nutrisi, atau meal plan...")
    if prompt:
        st.session_state.chat_history.append({"role": "user", "content": prompt, "ts": time.time()})
        st.markdown(f'<div class="chat-bubble-user">{prompt}</div>', unsafe_allow_html=True)

        with st.spinner("AI sedang memproses..."):
            try:
                if not food_database:
                    logger.error("Database makanan kosong.")
                    response_text = (
                        "(Error) Database makanan kosong. Periksa nutrition_db.py untuk memastikan data valid.\n"
                        "**Disclaimer**: Ini bukan saran medis profesional."
                    )
                elif model == "demo-echo":
                    response_text = (
                        "(Demo) Contoh resep bulking: **Ayam Panggang Madu**\n"
                        "- **Bahan**: 200g dada ayam, 2 sdm madu, 1 sdm minyak zaitun, nasi putih 150g.\n"
                        "- **Cara membuat**: Panggang ayam dengan madu dan minyak zaitun selama 20 menit. Sajikan dengan nasi.\n"
                        "- **Nutrisi**: ~600 kkal, 50g protein, 60g karbo, 15g lemak.\n"
                        "**Disclaimer**: Ini bukan saran medis profesional."
                    )
                else:
                    prompt_lower = prompt.lower()
                    # Deteksi jenis permintaan
                    if any(keyword in prompt_lower for keyword in ["meal plan", "rencana makan", "diet", "menu harian"]):
                        # Mode rencana makan
                        agent = MealPlannerAgent(call_chat_api, food_database)
                        days = 1 if "harian" in prompt_lower else 7
                        goal = {
                            "days": days,
                            "target_kcal_per_day": 2800 if "bulking" in prompt_lower or "menambah berat" in prompt_lower else 2000,
                            "min_protein_per_day": 120 if "tinggi protein" in prompt_lower or "bulking" in prompt_lower else 80,
                            "avoid": [],
                            "prefer": ["ayam", "nasi", "telur"] if any(x in prompt_lower for x in ["ayam", "nasi", "telur"]) else []
                        }
                        final = agent.iterate(goal)
                        response_text = format_meal_plan(final["final_report"], goal, prompt)
                    elif "resep" in prompt_lower or "recipe" in prompt_lower or "makanan" in prompt_lower:
                        # Mode resep spesifik
                        recipe_prompt = (
                            f"{general_food_prompt}\n"
                            "Pengguna meminta resep makanan. Berikan resep lengkap dengan:\n"
                            "- Nama hidangan kreatif\n"
                            "- Daftar bahan dengan takaran\n"
                            "- Langkah-langkah pembuatan secara detail\n"
                            "- Estimasi nutrisi (kalori, protein, karbohidrat, lemak)\n"
                            "- Tips untuk bulking (jika relevan, seperti porsi besar atau tambahan kalori)\n"
                            f"{negative_prompt}\n"
                            f"Pertanyaan pengguna: {prompt}"
                        )
                        response_text = call_chat_api(recipe_prompt, model)
                        if response_text.startswith("(Error)"):
                            response_text = (
                                f"(Error) Gagal memproses resep: {response_text}. Pastikan kunci API valid dan file encryption_key.key cocok.\n"
                                "**Disclaimer**: Ini bukan saran medis profesional."
                            )
                        else:
                            response_text = format_general_response(response_text)
                    else:
                        # Pertanyaan umum tentang makanan
                        full_prompt = f"{general_food_prompt}\n{negative_prompt}\nPertanyaan pengguna: {prompt}"
                        response_text = call_chat_api(full_prompt, model)
                        if response_text.startswith("(Error)"):
                            response_text = (
                                f"(Error) Gagal memproses pertanyaan: {response_text}. Pastikan kunci API valid dan file encryption_key.key cocok.\n"
                                "**Disclaimer**: Ini bukan saran medis profesional."
                            )
                        else:
                            response_text = format_general_response(response_text)
            except Exception as e:
                logger.error(f"Error di proses chat: {e}", exc_info=True)
                response_text = (
                    f"(Error) Terjadi kesalahan: {str(e)}. Pastikan file encryption_key.key ada, kunci API valid, dan izin file benar.\n"
                    "**Disclaimer**: Ini bukan saran medis profesional."
                )

            st.markdown(f'<div class="chat-bubble-assistant">{response_text}</div>', unsafe_allow_html=True)
            st.session_state.chat_history.append({"role": "assistant", "content": response_text, "ts": time.time()})

    cols = st.columns(3)
    with cols[0]:
        if st.button("💾 Ekspor Riwayat ke JSON"):
            ok, info = save_chat_history_to_file(st.session_state.chat_history)
            if ok:
                st.success(f"Disimpan ke {info} (enkripsi)")
                with open(info, "rb") as f:
                    st.download_button("Download file JSON (enkripsi)", f, file_name=info, mime="application/json")
            else:
                st.error(f"Gagal menyimpan: {info}")
    with cols[1]:
        if st.button("🗑️ Hapus Riwayat (Session)"):
            st.session_state.chat_history = []
            st.rerun()
    with cols[2]:
        st.write("")