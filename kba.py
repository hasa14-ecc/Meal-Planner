import json
import os
from typing import List, Dict, Any
from datetime import datetime
import streamlit as st
import pandas as pd
import re
from agent import get_encryption_key, encrypt_data, decrypt_data
from nutrition_db import get_nutrition_data
from chat import call_chat_api

def get_nutrition_from_grok(food_name: str) -> Dict[str, Any]:
    """
    Ambil data nutrisi dari Grok API berdasarkan nama makanan.
    """
    try:
        prompt = (
            f"Berikan informasi nutrisi untuk {food_name} per 100 gram dalam format berikut:\n"
            "- Kalori: [jumlah] kkal\n"
            "- Protein: [jumlah] g\n"
            "- Karbohidrat: [jumlah] g\n"
            "- Lemak: [jumlah] g\n"
            "Jika tidak tahu pasti, berikan estimasi berdasarkan pengetahuan umum."
        )
        response = call_chat_api(prompt)
        if response.startswith("(Error)"):
            st.error(f"Gagal mendapatkan data nutrisi dari Grok: {response}")
            return None

        # Ekstrak nilai nutrisi dari respon menggunakan regex
        kalori = re.search(r"Kalori: (\d+\.?\d*) kkal", response)
        protein = re.search(r"Protein: (\d+\.?\d*) g", response)
        karbo = re.search(r"Karbohidrat: (\d+\.?\d*) g", response)
        lemak = re.search(r"Lemak: (\d+\.?\d*) g", response)

        if not all([kalori, protein, karbo, lemak]):
            st.error(f"Grok tidak memberikan data nutrisi lengkap untuk '{food_name}'.")
            return None

        return {
            "name": food_name,
            "kalori": float(kalori.group(1)),
            "protein": float(protein.group(1)),
            "karbo": float(karbo.group(1)),
            "lemak": float(lemak.group(1)),
            "found": True
        }
    except Exception as e:
        st.error(f"Error saat memproses data nutrisi dari Grok: {str(e)}")
        return None

def add_meal_plan_to_history(meal_plan: Dict[str, Any], filename: str = "meal_plan_history.json") -> tuple[bool, str]:
    """
    Tambah meal plan ke riwayat dengan enkripsi file.
    """
    history = get_meal_plan_history(filename)
    history.append(meal_plan)
    try:
        encrypted = encrypt_data(json.dumps(history, ensure_ascii=False))
        with open(filename, "w", encoding="utf-8") as f:
            f.write(encrypted)
        return True, filename
    except Exception as e:
        return False, str(e)

def get_meal_plan_history(filename: str = "meal_plan_history.json") -> List[Dict[str, Any]]:
    """
    Ambil riwayat dari file enkripsi.
    """
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            encrypted = f.read()
            decrypted = decrypt_data(encrypted)
            if decrypted:
                return json.loads(decrypted)
    return []

def save_custom_foods(foods: List[Dict[str, Any]], filename: str = "custom_foods.json") -> bool:
    """
    Simpan makanan kustom ke file JSON.
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(foods, f, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Gagal menyimpan makanan kustom: {str(e)}")
        return False

def load_custom_foods(filename: str = "custom_foods.json") -> List[Dict[str, Any]]:
    """
    Muat makanan kustom dari file JSON.
    """
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Gagal memuat makanan kustom: {str(e)}")
            return []
    return []

def filter_history_by_date(history: List[Dict[str, Any]], date: str) -> List[Dict[str, Any]]:
    """
    Filter riwayat berdasarkan tanggal tertentu (format: YYYY-MM-DD).
    """
    return [plan for plan in history if plan.get("timestamp", "").startswith(date)]

def format_timestamp(timestamp: str) -> str:
    """
    Format timestamp ke bentuk ramah pengguna (misal: 25 Agustus 2025, 03:28).
    """
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        months = [
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember"
        ]
        return f"{dt.day} {months[dt.month-1]} {dt.year}, {dt.strftime('%H:%M')}"
    except ValueError:
        return timestamp

def app():
    """
    UI untuk input makanan real-time (dari database, kustom, atau Grok) dan tampil riwayat meal plan.
    """
    st.markdown("""
    <style>
    /* Background utama dengan warna abu-abu gelap */
    .stApp {
        background-color: #1A202C;
        font-family: 'Inter', sans-serif;
        color: #E2E8F0;
    }
    /* Header aplikasi */
    .app-header {
        background: linear-gradient(90deg, #2D3748, #1A202C 80%);
        color: #FFFFFF;
        padding: 20px 30px;
        border-radius: 12px;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        text-align: center;
        font-size: 28px;
        font-weight: 700;
    }
    /* Input section */
    .input-section {
        background-color: #2D3748;
        padding: 25px;
        border-radius: 12px;
        margin-bottom: 25px;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.3);
        border: 1px solid #4A5568;
    }
    .input-section h3 {
        color: #FFFFFF;
        font-size: 22px;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    /* Meal card untuk riwayat */
    .meal-card {
        background-color: #2A2E3B;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 3px 10px rgba(0, 0, 0, 0.3);
        border-left: 5px solid #2A9D8F;
    }
    .meal-card h3 {
        color: #FFFFFF;
        font-size: 20px;
        margin-bottom: 10px;
    }
    .meal-card h4 {
        color: #2A9D8F;
        font-size: 18px;
        margin-bottom: 15px;
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
    /* Styling untuk input teks */
    .stTextInput>div>input {
        border-radius: 8px;
        border: 1px solid #4A5568;
        padding: 10px;
        background-color: #2D3748;
        color: #FFFFFF;
    }
    /* Styling untuk selectbox */
    .stSelectbox>div>div {
        border-radius: 8px;
        border: 1px solid #4A5568;
        background-color: #2D3748;
        color: #FFFFFF;
    }
    /* Styling untuk number input */
    .stNumberInput>div>input {
        border-radius: 8px;
        border: 1px solid #4A5568;
        background-color: #2D3748;
        color: #FFFFFF;
    }
    /* Styling untuk tabel */
    .stTable {
        background-color: #2A2E3B;
        border-radius: 8px;
        border: 1px solid #4A5568;
        padding: 10px;
        color: #E2E8F0;
    }
    /* Styling untuk expander */
    .stExpander {
        background-color: #2D3748;
        border-radius: 12px;
        border: 1px solid #4A5568;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }
    .stExpander summary {
        background-color: #2A9D8F;
        color: #FFFFFF;
        border-radius: 12px 12px 0 0;
        padding: 15px;
        font-weight: 600;
        font-size: 18px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Header aplikasi
    st.markdown('<div class="app-header">🥗 AI Meal Planner</div>', unsafe_allow_html=True)

    # Inisialisasi session state untuk makanan kustom
    if "custom_foods" not in st.session_state:
        st.session_state.custom_foods = load_custom_foods()

    # Form untuk input makanan real-time (dari database, kustom, atau Grok)
    st.markdown('<div class="input-section"><h3>📥 Tambah Makanan ke Rencana</h3></div>', unsafe_allow_html=True)
    with st.form("meal_form"):
        day = st.text_input("Hari (contoh: Senin)", "Hari 1", placeholder="Masukkan hari")
        meal_type = st.selectbox("Jenis Makan", ["Sarapan", "Makan Siang", "Makan Malam", "Snack"])
        food_name = st.text_input("Nama Makanan", placeholder="Contoh: Ayam Goreng, Smoothie Protein")
        portion = st.number_input("Porsi (gram)", min_value=1.0, value=100.0, step=10.0)
        submit = st.form_submit_button("Tambah ke Rencana")

        if submit and food_name:
            # Cek di database dan makanan kustom terlebih dahulu
            food_names_db = get_nutrition_data()
            custom_food_names = {food["name"]: food for food in st.session_state.custom_foods}
            food_data = food_names_db.get(food_name) or custom_food_names.get(food_name)

            # Jika tidak ditemukan, coba ambil dari Grok
            if not food_data:
                food_data = get_nutrition_from_grok(food_name)
                if food_data and food_data["found"]:
                    # Tambahkan ke custom_foods agar bisa digunakan kembali
                    st.session_state.custom_foods.append(food_data)
                    if save_custom_foods(st.session_state.custom_foods):
                        st.success(f"Makanan '{food_name}' diambil dari Grok dan disimpan ke custom_foods.json!")
                    else:
                        st.error("Gagal menyimpan makanan dari Grok.")

            # Jika masih tidak ada data (Grok gagal), beri peringatan
            if not food_data:
                st.error(f"Makanan '{food_name}' tidak ditemukan di database atau Grok. Silakan tambahkan secara manual di form kustom.")
                return

            # Hitung nutrisi berdasarkan porsi
            portion_factor = portion / 100.0
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            meal_plan = {
                "timestamp": current_time,
                "day": day,
                "total_kalori": food_data.get("kalori", 0) * portion_factor,
                "total_protein": food_data.get("protein", 0.0) * portion_factor,
                "total_lemak": food_data.get("lemak", 0.0) * portion_factor,
                "total_karbohidrat": food_data.get("karbo", 0.0) * portion_factor,
                "meals": {
                    meal_type: [{
                        "name": food_name,
                        "kalori": food_data.get("kalori", 0) * portion_factor,
                        "protein": food_data.get("protein", 0.0) * portion_factor,
                        "lemak": food_data.get("lemak", 0.0) * portion_factor,
                        "karbohidrat": food_data.get("karbo", 0.0) * portion_factor,
                        "found": bool(food_data)
                    }]
                }
            }
            success, message = add_meal_plan_to_history(meal_plan)
            if success:
                st.success(f"Makanan '{food_name}' berhasil ditambahkan ke riwayat: {message}")
            else:
                st.error(f"Gagal menambahkan: {message}")

    # Form untuk menambah makanan kustom (manual fallback) dalam expander
    with st.expander("🍽️ Tambah Makanan Kustom (Manual)"):
        with st.form("custom_food_form"):
            food_name_manual = st.text_input("Nama Makanan (jika Grok gagal)", placeholder="Contoh: Nasi Uduk")
            calories = st.number_input("Kalori (kkal per 100g)", min_value=0.0, value=0.0, step=1.0)
            protein = st.number_input("Protein (g per 100g)", min_value=0.0, value=0.0, step=0.1)
            carbs = st.number_input("Karbohidrat (g per 100g)", min_value=0.0, value=0.0, step=0.1)
            fat = st.number_input("Lemak (g per 100g)", min_value=0.0, value=0.0, step=0.1)
            submit_custom = st.form_submit_button("Tambah Makanan Kustom")
            if submit_custom and food_name_manual:
                new_food = {
                    "name": food_name_manual,
                    "kalori": calories,
                    "protein": protein,
                    "karbo": carbs,
                    "lemak": fat,
                    "found": True
                }
                st.session_state.custom_foods.append(new_food)
                if save_custom_foods(st.session_state.custom_foods):
                    st.success(f"Makanan kustom '{food_name_manual}' ditambahkan secara manual!")
                else:
                    st.error("Gagal menyimpan makanan kustom.")

    # Tampilkan makanan kustom yang sudah ditambahkan
    if st.session_state.custom_foods:
        st.markdown('<div class="input-section"><h3>🍴 Daftar Makanan Kustom</h3></div>', unsafe_allow_html=True)
        custom_food_data = {
            "Nama": [food["name"] for food in st.session_state.custom_foods],
            "Kalori (kkal)": [food["kalori"] for food in st.session_state.custom_foods],
            "Protein (g)": [food["protein"] for food in st.session_state.custom_foods],
            "Karbohidrat (g)": [food["karbo"] for food in st.session_state.custom_foods],
            "Lemak (g)": [food["lemak"] for food in st.session_state.custom_foods]
        }
        st.table(pd.DataFrame(custom_food_data).style.format("{:.1f}", subset=["Kalori (kkal)", "Protein (g)", "Karbohidrat (g)", "Lemak (g)"]))

    # Tampilkan riwayat hari ini dengan expander
    current_date = datetime.now().strftime("%Y-%m-%d")
    history = get_meal_plan_history()
    today_history = filter_history_by_date(history, current_date)
    today_history = sorted(today_history, key=lambda x: x.get("timestamp", ""), reverse=True)  # Sort terbaru dulu

    with st.expander(f"📜 Riwayat Rencana Makan Hari Ini ({format_timestamp(current_date + ' 00:00:00')})", expanded=True):
        if not today_history:
            st.info("Belum ada riwayat rencana makan untuk hari ini.")
        else:
            for idx, plan in enumerate(today_history):
                st.markdown(f'<div class="meal-card">', unsafe_allow_html=True)
                st.markdown(f"### Rencana #{idx + 1} ({format_timestamp(plan.get('timestamp', 'Tanpa waktu'))})")
                day = plan.get("day", "Hari Tidak Diketahui")
                st.markdown(f"#### Hari {day}")

                # Tampilkan total nutrisi sebagai tabel
                total_data = {
                    "Kalori (kkal)": [plan.get("total_kalori", 0)],
                    "Protein (g)": [plan.get("total_protein", 0.0)],
                    "Lemak (g)": [plan.get("total_lemak", 0.0)],
                    "Karbohidrat (g)": [plan.get("total_karbohidrat", 0.0)]
                }
                df_total = pd.DataFrame(total_data)
                st.table(df_total.style.format("{:.1f}"))

                for meal, items in plan.get("meals", {}).items():
                    st.markdown(f"**{meal.capitalize()}:**")
                    for item in items:
                        name = item.get("name", "unknown")
                        kcal = item.get("kalori", 0)
                        prot = item.get("protein", 0.0)
                        fat = item.get("lemak", 0.0)
                        carb = item.get("karbohidrat", 0.0)
                        found = item.get("found", True)
                        status = "✅" if found else "⚠️ (tidak ditemukan)"
                        st.markdown(f"- {name}: {kcal:.1f} kkal, {prot:.1f} g protein, {fat:.1f} g lemak, {carb:.1f} g karbohidrat {status}")
                st.markdown("</div>", unsafe_allow_html=True)

    # Opsi untuk lihat semua riwayat dengan expander
    with st.expander("📜 Semua Riwayat Rencana Makan"):
        if not history:
            st.info("Belum ada riwayat rencana makan.")
        else:
            history = sorted(history, key=lambda x: x.get("timestamp", ""), reverse=True)
            for idx, plan in enumerate(history):
                st.markdown(f'<div class="meal-card">', unsafe_allow_html=True)
                st.markdown(f"### Rencana #{idx + 1} ({format_timestamp(plan.get('timestamp', 'Tanpa waktu'))})")
                day = plan.get("day", "Hari Tidak Diketahui")
                st.markdown(f"#### Hari {day}")

                # Tampilkan total nutrisi sebagai tabel
                total_data = {
                    "Kalori (kkal)": [plan.get("total_kalori", 0)],
                    "Protein (g)": [plan.get("total_protein", 0.0)],
                    "Lemak (g)": [plan.get("total_lemak", 0.0)],
                    "Karbohidrat (g)": [plan.get("total_karbohidrat", 0.0)]
                }
                df_total = pd.DataFrame(total_data)
                st.table(df_total.style.format("{:.1f}"))

                for meal, items in plan.get("meals", {}).items():
                    st.markdown(f"**{meal.capitalize()}:**")
                    for item in items:
                        name = item.get("name", "unknown")
                        kcal = item.get("kalori", 0)
                        prot = item.get("protein", 0.0)
                        fat = item.get("lemak", 0.0)
                        carb = item.get("karbohidrat", 0.0)
                        found = item.get("found", True)
                        status = "✅" if found else "⚠️ (tidak ditemukan)"
                        st.markdown(f"- {name}: {kcal:.1f} kkal, {prot:.1f} g protein, {fat:.1f} g lemak, {carb:.1f} g karbohidrat {status}")
                st.markdown("</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    app()