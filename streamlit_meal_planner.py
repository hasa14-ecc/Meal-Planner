import streamlit as st
import pandas as pd
import requests
from datetime import date, datetime
from typing import Dict, Any, List
import plotly.express as px
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
import logging
from agent import MealPlannerAgent
from nutrition_db import food_database
from prompts import pre_prompt_b, pre_breakfast, pre_prompt_l, pre_lunch, pre_prompt_d, pre_dinner
import kba as kba_module  # Import untuk akses fungsi history
import chat
import numpy as np
from kba import add_meal_plan_to_history  # Import fungsi simpan history

logger = logging.getLogger(__name__)

UNITS_CM_TO_IN = 0.393701
UNITS_KG_TO_LB = 2.20462

def calculate_bmr(weight: float, height: float, age: int, gender: str) -> float:
    """Menghitung Basal Metabolic Rate (BMR) berdasarkan Harris-Benedict."""
    if gender == "Pria":
        return 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
    else:
        return 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

def activity_multiplier(level: str) -> float:
    """Menentukan faktor aktivitas berdasarkan tingkat aktivitas."""
    mapping = {
        "Sangat Rendah (sedentary)": 1.2,
        "Rendah (ringan)": 1.375,
        "Sedang (aktivitas teratur)": 1.55,
        "Tinggi (aktif)": 1.725,
        "Sangat Tinggi (amat aktif)": 1.9
    }
    return mapping.get(level, 1.2)

def goal_adjustment(goal: str) -> int:
    """Menyesuaikan kalori berdasarkan tujuan (defisit, surplus, atau maintain)."""
    if goal == "Turun Berat (defisit)":
        return -500
    if goal == "Naik Berat (surplus)":
        return 300
    return 0

def generate_pdf_report(final_report: Dict[str, Any], name: str, target_kcal: float, target_protein: float) -> bytes:
    """Menghasilkan laporan PDF dari rencana makan."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(50, 750, f"Meal Plan Report untuk {name or 'User'}")
    c.drawString(50, 730, f"Target: {target_kcal:.0f} kkal/hari, {target_protein:.1f} g protein/hari")
    c.drawString(50, 710, f"Tanggal: {date.today()}")
    y = 680
    for day, info in final_report.items():
        c.drawString(50, y, f"Hari {day}:")
        y -= 20
        for meal, items in info["meals"].items():
            c.drawString(60, y, f"{meal.capitalize()}:")
            y -= 15
            for item in items:
                name = item.get("name", "unknown")
                kcal = item.get("kalori", 0)
                prot = item.get("protein", 0.0)
                karbo = item.get("karbo", 0.0)
                lemak = item.get("lemak", 0.0)
                c.drawString(70, y, f"- {name}: {kcal:.0f} kkal, {prot:.1f} g protein, {karbo:.1f} g karbo, {lemak:.1f} g lemak")
                y -= 15
            y -= 10
        c.drawString(60, y, f"Total: {info.get('total_kalori', 0):.0f} kkal, {info.get('total_protein', 0):.1f} g protein, "
                            f"{info.get('total_karbo', 0):.1f} g karbo, {info.get('total_lemak', 0):.1f} g lemak")
        y -= 30
        if y < 50:
            c.showPage()
            y = 750
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def create_nutrition_df(final_report: Dict[str, Any]) -> pd.DataFrame:
    """Membuat DataFrame untuk grafik distribusi makronutrien."""
    data = []
    for day, info in final_report.items():
        data.append({
            "Hari": f"Hari {day}",
            "Kalori (kkal)": info.get("total_kalori", 0),
            "Protein (g)": info.get("total_protein", 0),
            "Karbohidrat (g)": info.get("total_karbo", 0),
            "Lemak (g)": info.get("total_lemak", 0)
        })
    return pd.DataFrame(data)

def app():
    """Fungsi utama aplikasi Streamlit untuk perencanaan makan."""
    agent = MealPlannerAgent(chat.call_chat_api, food_database)
    st.markdown("""
    <style>
    .main-title {
        background: linear-gradient(90deg,#4CAF50,#388E3C 80%);
        color: white;
        padding: 20px 30px 14px 30px;
        border-radius: 12px;
        margin-bottom: 20px;
        box-shadow: 0 2px 8px rgba(44, 62, 80, 0.15);
        font-size: 24px;
        font-weight: 700;
        letter-spacing: 0.5px;
    }
    .input-card {
        background: #ffffff;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(44, 62, 80, 0.1);
        margin-bottom: 20px;
    }
    .disclaimer {
        color: red;
        font-style: italic;
        font-size: 14px;
        margin-top: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="main-title">🍽️ AI Meal Planner (Agentic AI, RAG)</div>', unsafe_allow_html=True)
    st.markdown("""
    Aplikasi ini membantu merencanakan makan harian/mingguan berdasarkan tujuan nutrisi Anda.<br>
    Masukkan data di bawah untuk menghitung kebutuhan kalori dan protein, lalu dapatkan rencana makan.<br>
    <p class='disclaimer'>Disclaimer: Ini bukan pengganti saran medis profesional. Konsultasikan dokter untuk kebutuhan nutrisi.</p>
    """, unsafe_allow_html=True)

    # Input pengguna
    with st.container():
        st.markdown('<div class="input-card"><b>Masukkan Data Anda</b>', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Nama", placeholder="Masukkan nama Anda")
            gender = st.selectbox("Jenis Kelamin", ["Pria", "Wanita"])
            age = st.number_input("Usia (tahun)", min_value=1, max_value=120, value=30)
        with col2:
            weight = st.number_input("Berat Badan (kg)", min_value=20.0, max_value=200.0, value=70.0)
            height = st.number_input("Tinggi Badan (cm)", min_value=100.0, max_value=250.0, value=170.0)
            activity = st.selectbox("Tingkat Aktivitas", [
                "Sangat Rendah (sedentary)", "Rendah (ringan)", "Sedang (aktivitas teratur)",
                "Tinggi (aktif)", "Sangat Tinggi (amat aktif)"
            ])
        goal = st.selectbox("Tujuan", ["Naik Berat (surplus)", "Turun Berat (defisit)", "Menjaga Berat"])
        days = st.number_input("Jumlah Hari Rencana Makan", min_value=1, max_value=14, value=7)
        avoid = st.text_input("Makanan yang Dihindari (pisahkan dengan koma)", placeholder="cth: daging babi, kacang")
        prefer = st.text_input("Makanan yang Disukai (pisahkan dengan koma)", placeholder="cth: ayam, nasi, telur")
        st.markdown('</div>', unsafe_allow_html=True)

    # Hitung kebutuhan nutrisi
    bmr = calculate_bmr(weight, height, age, gender)
    tdee = bmr * activity_multiplier(activity)
    target_kcal = tdee + goal_adjustment(goal)
    target_protein = weight * 1.6 if goal == "Naik Berat (surplus)" else weight * 1.2  # 1.6 g/kg untuk bulking

    st.markdown(f"**Kebutuhan Nutrisi Anda**:<br>Kalori: {target_kcal:.0f} kkal/hari<br>Protein: {target_protein:.1f} g/hari", unsafe_allow_html=True)

    # Tombol untuk menghasilkan rencana makan
    if st.button("Buat Rencana Makan"):
        with st.spinner("Membuat rencana makan..."):
            goal_dict = {
                "days": days,
                "target_kcal_per_day": target_kcal,
                "min_protein_per_day": target_protein,
                "avoid": [x.strip().lower() for x in avoid.split(",") if x.strip()],
                "prefer": [x.strip().lower() for x in prefer.split(",") if x.strip()]
            }
            try:
                result = agent.iterate(goal_dict)
                final_report = result["final_report"]
                eval_result = result["eval"]

                # Tabel Statistik
                st.markdown("### Statistik Rencana Makan")
                stats_data = []
                for day, info in final_report.items():
                    stats_data.append({
                        "Hari": f"Hari {day}",
                        "Kalori (kkal)": info.get("total_kalori", 0),
                        "Protein (g)": info.get("total_protein", 0),
                        "Karbohidrat (g)": info.get("total_karbo", 0),
                        "Lemak (g)": info.get("total_lemak", 0),
                        "% Target Kalori": info.get("pct_kcal", 0),
                        "% Target Protein": info.get("pct_protein", 0)
                    })
                stats_df = pd.DataFrame(stats_data)
                st.table(stats_df)

                # Ringkasan Statistik
                st.markdown("#### Ringkasan Statistik")
                stats = eval_result["stats"]
                corr_value = f"{stats['corr']:.2f}" if isinstance(stats['corr'], float) else stats['corr']
                st.markdown(f"""
                - **Rata-rata Kalori**: {stats['mean_kcal']:.0f} kkal/hari (Target: {target_kcal:.0f} kkal)
                - **Standar Deviasi Kalori**: {stats['std_kcal']:.0f} kkal
                - **Rata-rata Protein**: {stats['mean_protein']:.1f} g/hari (Target: {target_protein:.1f} g)
                - **Standar Deviasi Protein**: {stats['std_protein']:.1f} g
                - **Rata-rata Karbohidrat**: {stats['mean_karbo']:.1f} g/hari
                - **Standar Deviasi Karbohidrat**: {stats['std_karbo']:.1f} g
                - **Rata-rata Lemak**: {stats['mean_lemak']:.1f} g/hari
                - **Standar Deviasi Lemak**: {stats['std_lemak']:.1f} g
                - **Korelasi Kalori-Protein**: {corr_value}
                - **Sukses**: {'✅' if eval_result['success'] else '❌'} (Kalori ±10% dari target, protein ≥ target, variasi rendah)
                """)
                if eval_result["suggestions"]:
                    st.markdown("**Saran Perbaikan**:")
                    for sug in eval_result["suggestions"]:
                        st.markdown(f"- {sug}")

                # Grafik Makronutrien dengan Plotly
                st.markdown("#### Distribusi Makronutrien Harian")
                try:
                    df = create_nutrition_df(final_report)
                    if df.empty:
                        st.warning("Data nutrisi kosong. Tidak dapat membuat grafik.")
                    else:
                        df_melt = df.melt(id_vars=["Hari"], value_vars=["Kalori (kkal)", "Protein (g)", "Karbohidrat (g)", "Lemak (g)"],
                                          var_name="Nutrisi", value_name="Jumlah")
                        fig = px.bar(df_melt, x="Hari", y="Jumlah", color="Nutrisi", barmode="group",
                                     title="Distribusi Makronutrien Harian",
                                     labels={"Jumlah": "Jumlah", "Hari": "Hari"})
                        fig.update_layout(legend_title_text="Nutrisi", xaxis_title="Hari", yaxis_title="Jumlah")
                        st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.error(f"Gagal membuat grafik: {str(e)}. Pastikan data nutrisi lengkap.")

                # Detail Rencana Makan
                st.markdown("### Detail Rencana Makan")
                for day, info in final_report.items():
                    st.markdown(f"#### Hari {day}")
                    st.markdown(f"**Total**: {info.get('total_kalori', 0):.0f} kkal, {info.get('total_protein', 0):.1f} g protein, "
                                f"{info.get('total_karbo', 0):.1f} g karbo, {info.get('total_lemak', 0):.1f} g lemak")
                    for meal, items in info["meals"].items():
                        st.markdown(f"**{meal.capitalize()}:**")
                        if not items:
                            st.markdown("- Tidak ada makanan yang ditemukan untuk waktu makan ini.")
                            continue
                        for item in items:
                            name = item.get("name", "unknown")
                            kcal = item.get("kalori", 0)
                            prot = item.get("protein", 0.0)
                            karbo = item.get("karbo", 0.0)
                            lemak = item.get("lemak", 0.0)
                            found = item.get("found", True)
                            status = "✅" if found else "⚠️ (tidak ditemukan)"
                            st.markdown(f"- {name}: {kcal:.0f} kkal, {prot:.1f} g protein, {karbo:.1f} g karbo, {lemak:.1f} g lemak {status}")
                    st.markdown("")

                # Tombol Download PDF
                pdf_bytes = generate_pdf_report(final_report, name, target_kcal, target_protein)
                st.download_button(
                    label="📥 Download Rencana Makan (PDF)",
                    data=pdf_bytes,
                    file_name=f"meal_plan_{name or 'user'}_{date.today()}.pdf",
                    mime="application/pdf"
                )

                # RAG (Reasoning, Advice, Guidance)
                st.markdown("### RAG (Reasoning, Advice, Guidance)")
                st.markdown("""
                - **Reasoning**: Rencana makan disusun menggunakan database makanan yang luas dengan variasi tinggi, memastikan asupan kalori dan protein sesuai untuk bulking. Makanan dipilih dari berbagai kategori untuk mencegah pengulangan.
                - **Advice**: Tambahkan camilan tinggi kalori seperti kacang almond, protein shake, atau martabak manis di antara waktu makan untuk meningkatkan asupan kalori.
                - **Guidance**: Pantau kenaikan berat badan mingguan (target 0.5-1 kg untuk bulking). Jika kenaikan kurang, tingkatkan porsi atau frekuensi camilan.
                """)

                # Tombol Simpan ke History (manual)
                if st.button("💾 Simpan Rencana ke History"):
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    saved_count = 0
                    for day, info in final_report.items():
                        meal_plan = {
                            "timestamp": current_time,
                            "day": f"Hari {day}",
                            "total_kalori": info.get("total_kalori", 0),
                            "total_protein": info.get("total_protein", 0.0),
                            "total_lemak": info.get("total_lemak", 0.0),
                            "total_karbohidrat": info.get("total_karbo", 0.0),
                            "meals": info["meals"]
                        }
                        success, message = add_meal_plan_to_history(meal_plan)
                        if success:
                            saved_count += 1
                        else:
                            st.error(f"Gagal menyimpan Hari {day}: {message}")
                    if saved_count > 0:
                        st.success(f"{saved_count} hari berhasil disimpan ke history dengan timestamp real-time: {current_time}.")

            except Exception as e:
                st.error(f"Gagal membuat rencana makan: {str(e)}. Pastikan semua dependensi terinstal dan database makanan lengkap.")
                logger.error(f"Error in meal planning: {str(e)}")

if __name__ == "__main__":
    app()