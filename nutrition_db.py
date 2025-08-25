from typing import Dict, Optional, List
import requests
import logging
import json
import os
from retrying import retry

logger = logging.getLogger(__name__)

# Database makanan khas Indonesia dan internasional
# Format: "nama takaran": {"kalori": int, "protein": float, "karbo": float, "lemak": float}
food_database = {
    # Protein (Lauk Pauk)
    "telur_rebus (1 butir / 55g)": {"kalori": 78, "protein": 6.0, "karbo": 0.6, "lemak": 5.3},
    "telur_dadar (1 porsi / 65g)": {"kalori": 93, "protein": 7.0, "karbo": 0.8, "lemak": 6.5},
    "telur_ceplok (1 butir / 50g)": {"kalori": 90, "protein": 6.0, "karbo": 0.5, "lemak": 7.0},
    "tahu_goreng (1 potong / 50g)": {"kalori": 80, "protein": 4.0, "karbo": 2.0, "lemak": 6.0},
    "tempe_goreng (1 potong / 50g)": {"kalori": 110, "protein": 6.0, "karbo": 5.0, "lemak": 8.0},
    "tempe_bacem (1 potong / 50g)": {"kalori": 120, "protein": 5.5, "karbo": 8.0, "lemak": 7.0},
    "ayam_goreng (1 potong / 100g)": {"kalori": 260, "protein": 27.0, "karbo": 0.0, "lemak": 15.0},
    "ayam_rebus (1 potong / 100g)": {"kalori": 165, "protein": 25.0, "karbo": 0.0, "lemak": 6.0},
    "ayam_suwir (50g)": {"kalori": 95, "protein": 9.0, "karbo": 0.0, "lemak": 6.0},
    "ayam_opor (1 porsi / 150g)": {"kalori": 200, "protein": 18.0, "karbo": 5.0, "lemak": 12.0},
    "ayam_rendang (1 porsi / 100g)": {"kalori": 220, "protein": 20.0, "karbo": 3.0, "lemak": 14.0},
    "ayam_bakar (1 potong / 100g)": {"kalori": 180, "protein": 22.0, "karbo": 2.0, "lemak": 8.0},
    "ikan_tuna_suwir (50g)": {"kalori": 85, "protein": 10.0, "karbo": 0.0, "lemak": 4.0},
    "ikan_goreng (1 ekor / 80g)": {"kalori": 150, "protein": 20.0, "karbo": 0.0, "lemak": 8.0},
    "ikan_bakar (1 ekor / 80g)": {"kalori": 120, "protein": 18.0, "karbo": 0.0, "lemak": 4.0},
    "ikan_salmon_panggang (100g)": {"kalori": 206, "protein": 22.0, "karbo": 0.0, "lemak": 13.0},
    "daging_sapi_giling (50g)": {"kalori": 120, "protein": 11.0, "karbo": 0.0, "lemak": 8.0},
    "daging_sapi_tumis (50g)": {"kalori": 130, "protein": 12.0, "karbo": 1.0, "lemak": 8.0},
    "rendang_sapi (1 porsi / 100g)": {"kalori": 280, "protein": 22.0, "karbo": 5.0, "lemak": 20.0},
    "sate_ayam (5 tusuk / 100g)": {"kalori": 200, "protein": 18.0, "karbo": 5.0, "lemak": 12.0},
    "sate_kambing (5 tusuk / 100g)": {"kalori": 250, "protein": 20.0, "karbo": 4.0, "lemak": 18.0},
    "udang_goreng (50g)": {"kalori": 110, "protein": 12.0, "karbo": 1.0, "lemak": 6.0},
    "udang_rebus (50g)": {"kalori": 60, "protein": 12.0, "karbo": 0.0, "lemak": 1.0},
    "kepiting_saus_tiram (1 porsi / 100g)": {"kalori": 150, "protein": 15.0, "karbo": 5.0, "lemak": 8.0},
    "tahu_telur (1 porsi / 150g)": {"kalori": 220, "protein": 12.0, "karbo": 10.0, "lemak": 15.0},
    # Karbohidrat
    "nasi_putih (1 centong / 100g)": {"kalori": 175, "protein": 3.5, "karbo": 40.0, "lemak": 0.5},
    "nasi_uduk (1 porsi / 100g)": {"kalori": 200, "protein": 4.0, "karbo": 35.0, "lemak": 5.0},
    "nasi_kuning (1 porsi / 150g)": {"kalori": 250, "protein": 5.0, "karbo": 45.0, "lemak": 6.0},
    "nasi_goreng (1 porsi / 200g)": {"kalori": 320, "protein": 10.0, "karbo": 45.0, "lemak": 12.0},
    "nasi_merah (1 centong / 100g)": {"kalori": 110, "protein": 2.5, "karbo": 23.0, "lemak": 0.9},
    "lontong (1 potong / 60g)": {"kalori": 80, "protein": 2.0, "karbo": 18.0, "lemak": 0.5},
    "ketupat (1 potong / 100g)": {"kalori": 140, "protein": 3.0, "karbo": 30.0, "lemak": 1.0},
    "roti_tawar (1 lembar / 25g)": {"kalori": 67, "protein": 2.0, "karbo": 12.0, "lemak": 1.0},
    "roti_gandum (1 lembar / 30g)": {"kalori": 80, "protein": 2.5, "karbo": 14.0, "lemak": 1.2},
    "bubur_ayam (1 mangkuk / 250g)": {"kalori": 280, "protein": 9.0, "karbo": 45.0, "lemak": 8.0},
    "mie_goreng (1 porsi / 200g)": {"kalori": 400, "protein": 12.0, "karbo": 50.0, "lemak": 18.0},
    "bihun_goreng (1 porsi / 200g)": {"kalori": 350, "protein": 8.0, "karbo": 60.0, "lemak": 10.0},
    "kwetiau_goreng (1 porsi / 200g)": {"kalori": 380, "protein": 10.0, "karbo": 55.0, "lemak": 15.0},
    "ubi_rebus (1 potong / 100g)": {"kalori": 120, "protein": 1.0, "karbo": 28.0, "lemak": 0.1},
    "kentang_rebus (1 porsi / 100g)": {"kalori": 87, "protein": 2.0, "karbo": 20.0, "lemak": 0.1},
    "kentang_goreng (1 porsi / 100g)": {"kalori": 312, "protein": 3.4, "karbo": 41.0, "lemak": 15.0},
    "singkong_rebus (1 potong / 100g)": {"kalori": 146, "protein": 1.0, "karbo": 35.0, "lemak": 0.3},
    "jagung_rebus (1 tongkol / 100g)": {"kalori": 96, "protein": 3.4, "karbo": 21.0, "lemak": 1.5},
    "pasta_spaghetti (1 porsi / 100g)": {"kalori": 131, "protein": 5.0, "karbo": 25.0, "lemak": 1.0},
    "roti_canai (1 lembar / 100g)": {"kalori": 300, "protein": 6.0, "karbo": 45.0, "lemak": 10.0},
    # Sayuran
    "sayur_kolplay (1 porsi / 100g)": {"kalori": 45, "protein": 2.0, "karbo": 7.0, "lemak": 1.5},
    "sayur_bayam (1 porsi / 100g)": {"kalori": 23, "protein": 2.9, "karbo": 3.6, "lemak": 0.4},
    "capcay (1 porsi / 150g)": {"kalori": 90, "protein": 3.0, "karbo": 10.0, "lemak": 4.0},
    "sop_sayur (1 mangkuk / 200g)": {"kalori": 60, "protein": 2.0, "karbo": 8.0, "lemak": 2.0},
    "kangkung_tumis (1 porsi / 100g)": {"kalori": 50, "protein": 2.0, "karbo": 5.0, "lemak": 3.0},
    "brokoli_kukus (1 porsi / 100g)": {"kalori": 35, "protein": 2.8, "karbo": 7.0, "lemak": 0.4},
    "wortel_rebus (1 porsi / 100g)": {"kalori": 41, "protein": 0.9, "karbo": 9.6, "lemak": 0.2},
    "lalapan (1 porsi / 100g)": {"kalori": 20, "protein": 1.0, "karbo": 4.0, "lemak": 0.2},
    # Buah
    "pisang (1 buah / 100g)": {"kalori": 90, "protein": 1.1, "karbo": 22.8, "lemak": 0.3},
    "jeruk (1 buah / 100g)": {"kalori": 47, "protein": 0.9, "karbo": 11.8, "lemak": 0.1},
    "mangga (1 buah / 150g)": {"kalori": 90, "protein": 1.2, "karbo": 22.5, "lemak": 0.6},
    "semangka (1 potong / 100g)": {"kalori": 30, "protein": 0.6, "karbo": 7.5, "lemak": 0.2},
    "melon (1 potong / 100g)": {"kalori": 34, "protein": 0.8, "karbo": 8.2, "lemak": 0.2},
    "alpukat (1 buah / 100g)": {"kalori": 160, "protein": 2.0, "karbo": 8.5, "lemak": 14.7},
    # Minuman
    "teh_manis (1 gelas / 200ml)": {"kalori": 80, "protein": 0.0, "karbo": 20.0, "lemak": 0.0},
    "kopi_susu (1 gelas / 200ml)": {"kalori": 100, "protein": 2.0, "karbo": 12.0, "lemak": 4.0},
    "jus_jeruk (1 gelas / 200ml)": {"kalori": 94, "protein": 1.4, "karbo": 22.0, "lemak": 0.4},
    "susu_cokelat (1 gelas / 200ml)": {"kalori": 140, "protein": 6.0, "karbo": 20.0, "lemak": 4.0},
    "air_putih (1 gelas / 200ml)": {"kalori": 0, "protein": 0.0, "karbo": 0.0, "lemak": 0.0},
    # Camilan
    "pisang_goreng (1 buah / 50g)": {"kalori": 120, "protein": 1.0, "karbo": 20.0, "lemak": 4.0},
    "tahu_isi (1 buah / 50g)": {"kalori": 100, "protein": 3.0, "karbo": 10.0, "lemak": 5.0},
    "martabak_manis (1 potong / 100g)": {"kalori": 270, "protein": 5.0, "karbo": 40.0, "lemak": 10.0},
    "keripik_kentang (1 porsi / 50g)": {"kalori": 270, "protein": 3.0, "karbo": 28.0, "lemak": 15.0},
    "kacang_tanah (1 porsi / 30g)": {"kalori": 170, "protein": 7.0, "karbo": 5.0, "lemak": 14.0},
    "roti_bakar (1 lembar / 50g)": {"kalori": 150, "protein": 3.0, "karbo": 25.0, "lemak": 4.0},
}

# Kategori makanan untuk breakfast, lunch, dinner
food_items_breakfast = {
    "protein": {k: v for k, v in food_database.items() if any(x in k for x in ["telur", "tahu", "tempe", "ayam", "ikan"])},
    "karbohidrat": {k: v for k, v in food_database.items() if any(x in k for x in ["nasi", "roti", "bubur", "lontong"])},
    "sayuran": {k: v for k, v in food_database.items() if any(x in k for x in ["sayur", "kolplay", "bayam", "brokoli", "wortel"])},
    "buah": {k: v for k, v in food_database.items() if any(x in k for x in ["pisang", "jeruk", "mangga", "semangka", "melon", "alpukat"])},
    "minuman": {k: v for k, v in food_database.items() if any(x in k for x in ["teh", "kopi", "jus", "susu", "air"])},
    "camilan": {k: v for k, v in food_database.items() if any(x in k for x in ["roti", "pisang_goreng", "tahu_isi", "kacang"])}
}

food_items_lunch = {
    "protein": {k: v for k, v in food_database.items() if any(x in k for x in ["ayam", "ikan", "daging", "tahu", "tempe", "udang"])},
    "karbohidrat": {k: v for k, v in food_database.items() if any(x in k for x in ["nasi", "mie", "kentang", "lontong", "ketupat", "pasta"])},
    "sayuran": {k: v for k, v in food_database.items() if any(x in k for x in ["sayur", "sop", "capcay", "kangkung", "brokoli", "wortel"])},
    "buah": {k: v for k, v in food_database.items() if any(x in k for x in ["jeruk", "mangga", "semangka", "melon", "alpukat"])},
    "minuman": {k: v for k, v in food_database.items() if any(x in k for x in ["teh", "kopi", "jus", "es", "air"])},
    "camilan": {k: v for k, v in food_database.items() if any(x in k for x in ["keripik", "pisang_goreng", "tahu_isi", "martabak", "kacang"])}
}

food_items_dinner = {
    "protein": {k: v for k, v in food_database.items() if any(x in k for x in ["ikan", "tahu", "tempe", "udang", "ayam", "daging"])},
    "karbohidrat": {k: v for k, v in food_database.items() if any(x in k for x in ["nasi", "kentang", "ubi", "pasta", "singkong", "jagung"])},
    "sayuran": {k: v for k, v in food_database.items() if any(x in k for x in ["sayur", "sop", "lalapan", "kangkung", "brokoli", "wortel"])},
    "buah": {k: v for k, v in food_database.items() if any(x in k for x in ["pisang", "melon", "semangka", "jeruk", "mangga", "alpukat"])},
    "minuman": {k: v for k, v in food_database.items() if any(x in k for x in ["teh", "jus", "susu", "air"])},
    "camilan": {k: v for k, v in food_database.items() if any(x in k for x in ["kacang", "keripik", "roti_bakar", "martabak"])}
}

def _clean(mealdict: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, Dict[str, float]]]:
    cleaned = {}
    for cat, items in mealdict.items():
        cleaned[cat] = {}
        for k, v in items.items():
            if k and k in food_database and all(key in v for key in ["kalori", "protein", "karbo", "lemak"]):
                cleaned[cat][k] = v
            else:
                logger.warning(f"Makanan {k} dihapus dari kategori {cat} karena tidak valid atau tidak ada di food_database.")
    return cleaned

# Clean kategori
food_items_breakfast = _clean(food_items_breakfast)
food_items_lunch = _clean(food_items_lunch)
food_items_dinner = _clean(food_items_dinner)

def validate_nutrition_data(data: Dict[str, Dict[str, float]]) -> bool:
    for food, nutrients in data.items():
        if not all(key in nutrients for key in ["kalori", "protein", "karbo", "lemak"]):
            logger.error(f"Data nutrisi tidak lengkap untuk {food}")
            return False
        for key, value in nutrients.items():
            if not isinstance(value, (int, float)) or value < 0:
                logger.error(f"Nilai nutrisi tidak valid untuk {food}: {key} = {value}")
                return False
    return True

@retry(stop_max_attempt_number=3, wait_fixed=2000)
def fetch_from_open_food_facts(term: str, api_url: str = "https://world.openfoodfacts.org/api/v2") -> Optional[Dict]:
    headers = {"User-Agent": "AI-Meal-Planner - Python - Version 1.0"}
    url = f"{api_url}/search?search_terms={term}&fields=product_name,nutriments"
    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Gagal mengambil data untuk {term}: {e}")
        raise

def update_food_database_from_api(
    search_terms: List[str],
    api_url: str = "https://world.openfoodfacts.org/api/v2",
    filename: str = "food_database.json"
) -> None:
    new_foods = {}
    for term in search_terms:
        try:
            data = fetch_from_open_food_facts(term, api_url)
            if data.get("products"):
                for product in data["products"]:
                    name = product.get("product_name", "").lower()
                    if name and name not in food_database:
                        nutriments = product.get("nutriments", {})
                        calories = nutriments.get("energy-kcal_100g", 0)
                        protein = nutriments.get("proteins_100g", 0)
                        carbs = nutriments.get("carbohydrates_100g", 0)
                        fat = nutriments.get("fat_100g", 0)
                        if calories and protein and carbs and fat:
                            new_foods[f"{name} (100g)"] = {
                                "kalori": round(float(calories)),
                                "protein": round(float(protein), 1),
                                "karbo": round(float(carbs), 1),
                                "lemak": round(float(fat), 1)
                            }
        except Exception as e:
            logger.warning(f"Gagal mengambil data untuk {term}: {e}")
            continue

    if validate_nutrition_data(new_foods):
        food_database.update(new_foods)
        logger.info(f"Berhasil menambahkan {len(new_foods)} makanan baru ke database.")
    else:
        logger.error("Validasi data baru gagal, tidak mengupdate food_database.")
        return

    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(food_database, f, ensure_ascii=False, indent=2)
        logger.info(f"Database diperbarui dan disimpan ke {filename}")
    except Exception as e:
        logger.error(f"Gagal menyimpan database: {e}")

def load_food_database_from_file(filename: str = "food_database.json") -> None:
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
                if validate_nutrition_data(loaded_data):
                    food_database.update(loaded_data)
                    logger.info(f"Database dimuat dari {filename}")
                else:
                    logger.error(f"Data dari {filename} tidak valid, tidak dimuat.")
        else:
            logger.info(f"File {filename} tidak ditemukan, menggunakan database default.")
    except Exception as e:
        logger.error(f"Gagal memuat database dari {filename}: {e}")

def get_nutrition_data(food_name: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    if food_name:
        food_data = food_database.get(food_name.lower())
        if not food_data:
            logger.warning(f"Makanan {food_name} tidak ditemukan di database.")
        return food_data
    return food_database

def categorize_food(food_name: str) -> Optional[str]:
    food_data = get_nutrition_data(food_name)
    if not food_data:
        return None

    protein = food_data.get("protein", 0)
    karbo = food_data.get("karbo", 0)
    lemak = food_data.get("lemak", 0)

    if "sayur" in food_name.lower() or "kangkung" in food_name.lower() or "brokoli" in food_name.lower():
        return "sayuran"
    elif "pisang" in food_name.lower() or "jeruk" in food_name.lower() or "mangga" in food_name.lower():
        return "buah"
    elif "teh" in food_name.lower() or "kopi" in food_name.lower() or "jus" in food_name.lower():
        return "minuman"
    elif "keripik" in food_name.lower() or "martabak" in food_name.lower() or "kacang" in food_name.lower():
        return "camilan"
    elif protein > karbo and protein > lemak:
        return "protein"
    elif karbo > protein and karbo > lemak:
        return "karbohidrat"
    elif lemak > protein and lemak > karbo:
        return "lemak"
    return None

search_terms = [
    "nasi", "ayam", "ikan", "tempe", "tahu", "sapi", "rendang", "sate", "soto", "rawon",
    "bakso", "mie", "bihun", "kwetiau", "sayur", "capcay", "gado", "pecel", "pisang",
    "alpukat", "mangga", "jeruk", "susu", "keju", "yogurt", "kacang", "keripik",
    "martabak", "roti", "pasta", "pizza", "burger", "sushi", "smoothie", "protein shake",
    "brokoli", "wortel", "kangkung", "semangka", "melon", "alpukat", "teh hijau", "es teh"
]

if not validate_nutrition_data(food_database):
    logger.error("Database awal tidak valid, silakan periksa data nutrisi.")
else:
    logger.info("Database awal valid.")

load_food_database_from_file()
# update_food_database_from_api(search_terms)  # Uncomment jika ingin update dari API