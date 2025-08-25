import streamlit as st
import streamlit_meal_planner
import kba
import chat
import logging
from datetime import datetime

# Setup logging untuk seluruh app
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Fungsi utama untuk run app Streamlit.
    Handle error global dengan logging.
    """
    try:
        st.set_page_config(
            page_title="Agentic AI Meal Planner",
            page_icon="🍽️",
            layout="wide",
            initial_sidebar_state="expanded"
        )
        st.sidebar.title("Navigasi")
        st.sidebar.markdown(f"**Last Update:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        app_mode = st.sidebar.selectbox(
            "Pilih Mode",
            ["Perencana Makan", "Riwayat", "Chat"],
            help="Pilih mode aplikasi untuk perencanaan makan, melihat riwayat, atau chat interaktif."
        )

        logger.info(f"Memulai aplikasi dengan mode: {app_mode}")

        if app_mode == "Perencana Makan":
            streamlit_meal_planner.app()
        elif app_mode == "Riwayat":
            kba.app()
        elif app_mode == "Chat":
            chat.app()
    except Exception as e:
        logger.error(f"Error di aplikasi utama: {str(e)}", exc_info=True)
        st.error(f"Terjadi kesalahan: {str(e)}. Silakan coba lagi atau hubungi support.")

if __name__ == "__main__":
    main()