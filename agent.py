import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from sentence_transformers import SentenceTransformer, util
import streamlit as st
import requests
import json
from cryptography.fernet import Fernet, InvalidToken
import os
import numpy as np
from scipy import stats
import random

logger = logging.getLogger(__name__)

def get_encryption_key():
    key_path = "encryption_key.key"
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(key_path, "wb") as f:
            f.write(key)
    return Fernet(key)

def encrypt_data(data: str) -> str:
    encryption_key = get_encryption_key()
    return encryption_key.encrypt(data.encode()).decode()

def decrypt_data(encrypted: str) -> str:
    encryption_key = get_encryption_key()
    try:
        return encryption_key.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        logger.error("Invalid encryption token.")
        return ""

class MealPlannerAgent:
    def __init__(self, call_chat_api_func: callable, food_db: Dict[str, Dict[str, float]], model: str = "llama-3.3-70b-versatile"):
        self.call_chat_api = call_chat_api_func
        self.food_db = {k.lower(): v for k, v in food_db.items()}
        self.model = model
        self.trace: List[Dict[str, Any]] = []
        try:
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        except Exception as e:
            logger.warning(f"Gagal inisialisasi sentence-transformers: {e}. Menggunakan retrieval sederhana.")
            self.embedding_model = None
        self.open_food_facts_api_url = st.secrets.get("OPEN_FOOD_FACTS_API_URL", "https://world.openfoodfacts.org/api/v2")
        self.used_foods = {}

    def _retrieve_relevant_foods(self, goal: Dict[str, Any], meal_type: str, day: int) -> List[str]:
        """
        Ambil daftar makanan relevan dengan variasi maksimal.
        """
        from nutrition_db import food_items_breakfast, food_items_lunch, food_items_dinner
        meal_dict = {
            "breakfast": food_items_breakfast,
            "lunch": food_items_lunch,
            "dinner": food_items_dinner
        }
        categories = meal_dict[meal_type]
        avoid = [a.lower() for a in goal.get("avoid", [])]
        prefer = [p.lower() for p in goal.get("prefer", [])]
        used_foods_day = self.used_foods.get(day, set())

        relevant = []
        for cat, items in categories.items():
            available = [k for k in items.keys() if k not in used_foods_day and all(a not in k for a in avoid)]
            if not available:
                continue
            if prefer:
                available = sorted(
                    available,
                    key=lambda k: (sum(p in k for p in prefer), items[k].get("kalori", 0) + items[k].get("protein", 0) * 4),
                    reverse=True
                )
            else:
                available = sorted(
                    available,
                    key=lambda k: items[k].get("kalori", 0) + items[k].get("protein", 0) * 4,
                    reverse=True
                )
            relevant.extend(available[:2])
        random.shuffle(relevant)
        return relevant[:3]

    def _fuzzy_find(self, name: Any) -> Optional[str]:
        if isinstance(name, dict):
            name = name.get("name", str(name))
        if not isinstance(name, str):
            name = str(name)
        s = name.lower().strip()
        
        if s in self.food_db:
            return s

        if self.embedding_model:
            query_emb = self.embedding_model.encode(s)
            food_embs = {k: self.embedding_model.encode(k) for k in self.food_db.keys()}
            scores = {k: util.cos_sim(query_emb, emb)[0][0].item() for k, emb in food_embs.items()}
            best = max(scores, key=scores.get)
            if scores[best] > 0.75:
                return best

        for k in self.food_db.keys():
            if re.search(r'\b' + re.escape(s) + r'\b', k):
                return k

        try:
            url = f"{self.open_food_facts_api_url}/search?search_terms={s}&fields=product_name,nutriments"
            headers = {"User-Agent": "AI-Meal-Planner - Python - Version 1.0"}
            resp = requests.get(url, headers=headers, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if data.get("products"):
                product = data["products"][0]
                name = product.get("product_name", "").lower()
                nutriments = product.get("nutriments", {})
                calories = nutriments.get("energy-kcal_100g", 0)
                protein = nutriments.get("proteins_100g", 0)
                carbs = nutriments.get("carbohydrates_100g", 0)
                fat = nutriments.get("fat_100g", 0)
                if calories and protein and carbs and fat:
                    self.food_db[name] = {
                        "kalori": round(calories),
                        "protein": round(protein, 1),
                        "karbo": round(carbs, 1),
                        "lemak": round(fat, 1)
                    }
                    return name
        except Exception as e:
            logger.warning(f"Gagal mengambil data dari API untuk {s}: {e}")

        return None

    def _validate_nutrition(self, plan: Dict[str, Any], goal: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Validasi nutrisi: cek target kalori, protein, dan variasi.
        """
        kcal_per_day = []
        protein_per_day = []
        karbo_per_day = []
        lemak_per_day = []
        pct_kcal = []
        pct_protein = []
        suggestions = []

        target_kcal = goal.get("target_kcal_per_day", 1)
        target_protein = goal.get("min_protein_per_day", 1)

        for day, info in plan.items():
            total_kcal = sum(sum(item.get("kalori", 0) for item in items) for items in info.get("meals", {}).values())
            total_protein = sum(sum(item.get("protein", 0) for item in items) for items in info.get("meals", {}).values())
            total_karbo = sum(sum(item.get("karbo", 0) for item in items) for items in info.get("meals", {}).values())
            total_lemak = sum(sum(item.get("lemak", 0) for item in items) for items in info.get("meals", {}).values())
            info["total_kalori"] = total_kcal
            info["total_protein"] = total_protein
            info["total_karbo"] = total_karbo
            info["total_lemak"] = total_lemak
            pct_k = (total_kcal / target_kcal * 100) if target_kcal != 0 else 0
            pct_p = (total_protein / target_protein * 100) if target_protein != 0 else 0
            info["pct_kcal"] = pct_k
            info["pct_protein"] = pct_p
            kcal_per_day.append(total_kcal)
            protein_per_day.append(total_protein)
            karbo_per_day.append(total_karbo)
            lemak_per_day.append(total_lemak)
            pct_kcal.append(pct_k)
            pct_protein.append(pct_p)
            if pct_k < 90 or pct_k > 110:
                suggestions.append(f"Hari {day}: Kalori {pct_k:.1f}% dari target, sesuaikan porsi.")
            if pct_p < 100:
                suggestions.append(f"Hari {day}: Protein {pct_p:.1f}% dari min, tambah protein.")

        mean_kcal = np.mean(kcal_per_day) if kcal_per_day else 0
        std_kcal = np.std(kcal_per_day) if kcal_per_day else 0
        mean_protein = np.mean(protein_per_day) if protein_per_day else 0
        std_protein = np.std(protein_per_day) if protein_per_day else 0
        mean_karbo = np.mean(karbo_per_day) if karbo_per_day else 0
        std_karbo = np.std(karbo_per_day) if karbo_per_day else 0
        mean_lemak = np.mean(lemak_per_day) if lemak_per_day else 0
        std_lemak = np.std(lemak_per_day) if lemak_per_day else 0
        corr = stats.pearsonr(kcal_per_day, protein_per_day)[0] if len(kcal_per_day) > 1 else np.nan

        success = all(90 <= p <= 110 for p in pct_kcal) and all(p >= 100 for p in pct_protein) and std_kcal < target_kcal * 0.1

        eval_result = {
            "success": success,
            "stats": {
                "mean_kcal": mean_kcal,
                "std_kcal": std_kcal,
                "mean_protein": mean_protein,
                "std_protein": std_protein,
                "mean_karbo": mean_karbo,
                "std_karbo": std_karbo,
                "mean_lemak": mean_lemak,
                "std_lemak": std_lemak,
                "corr": corr
            },
            "suggestions": suggestions
        }
        return success, eval_result

    def plan(self, goal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Buat rencana makan awal.
        """
        days = goal.get("days", 7)
        target_kcal_per_day = goal.get("target_kcal_per_day", 1)
        target_protein_per_day = goal.get("min_protein_per_day", 1)
        target_kcal_per_meal = target_kcal_per_day / 3
        target_protein_per_meal = target_protein_per_day / 3
        plan = {}

        for day in range(1, days + 1):
            self.used_foods[day] = set()
            meals = {}
            for meal_type in ["breakfast", "lunch", "dinner"]:
                relevant_foods = self._retrieve_relevant_foods(goal, meal_type, day)
                selected_foods = []
                meal_kcal = 0
                meal_protein = 0
                for food in relevant_foods:
                    found = self._fuzzy_find(food)
                    if found and found in self.food_db:
                        base_kcal = self.food_db[found].get("kalori", 0)
                        base_protein = self.food_db[found].get("protein", 0.0)
                        base_karbo = self.food_db[found].get("karbo", 0.0)
                        base_lemak = self.food_db[found].get("lemak", 0.0)
                        if base_kcal == 0:
                            logger.warning(f"Makanan {found} memiliki kalori 0, menggunakan porsi default 100g.")
                            portion_g = 100
                        else:
                            portion_g = max(100, target_kcal_per_meal / 3 / (base_kcal / 100))
                        portion_g = min(portion_g, 300)
                        kcal = (base_kcal * portion_g) / 100
                        protein = (base_protein * portion_g) / 100
                        karbo = (base_karbo * portion_g) / 100
                        lemak = (base_lemak * portion_g) / 100
                        
                        if meal_kcal + kcal <= target_kcal_per_meal * 1.2:
                            selected_foods.append({
                                "name": f"{found} ({int(portion_g)}g)",
                                "kalori": kcal,
                                "protein": protein,
                                "karbo": karbo,
                                "lemak": lemak,
                                "found": True
                            })
                            meal_kcal += kcal
                            meal_protein += protein
                            self.used_foods[day].add(found)
                            if len(selected_foods) >= 3 or meal_kcal >= target_kcal_per_meal * 0.8:
                                break
                
                meals[meal_type] = selected_foods if selected_foods else [
                    {"name": "tidak ditemukan", "kalori": 0, "protein": 0, "karbo": 0, "lemak": 0, "found": False}
                ]
            plan[str(day)] = {
                "meals": meals,
                "total_kalori": sum(sum(item.get("kalori", 0) for item in meal_items) for meal_items in meals.values()),
                "total_protein": sum(sum(item.get("protein", 0) for item in meal_items) for meal_items in meals.values()),
                "total_karbo": sum(sum(item.get("karbo", 0) for item in meal_items) for meal_items in meals.values()),
                "total_lemak": sum(sum(item.get("lemak", 0) for item in meal_items) for meal_items in meals.values()),
                "pct_kcal": (sum(sum(item.get("kalori", 0) for item in meal_items) for meal_items in meals.values()) / target_kcal_per_day * 100) if target_kcal_per_day != 0 else 0,
                "pct_protein": (sum(sum(item.get("protein", 0) for item in meal_items) for meal_items in meals.values()) / target_protein_per_day * 100) if target_protein_per_day != 0 else 0
            }
        return plan

    def iterate(self, goal: Dict[str, Any], max_iters: int = 3) -> Dict[str, Any]:
        """
        Iterasi untuk memperbaiki rencana makan.
        """
        days = goal.get("days", 7)
        target_kcal_per_day = goal.get("target_kcal_per_day", 1)
        target_protein_per_day = goal.get("min_protein_per_day", 1)
        plan = self.plan(goal)
        success, eval_result = self._validate_nutrition(plan, goal)
        self.trace.append({"plan": plan, "eval": eval_result})
        
        for _ in range(max_iters - 1):
            if success:
                break
            for day, meals in plan.items():
                for meal_type, items in meals.get("meals", {}).items():
                    meal_kcal = sum(item.get("kalori", 0) for item in items)
                    meal_protein = sum(item.get("protein", 0) for item in items)
                    if meal_kcal < (target_kcal_per_day / 3 * 0.8) or meal_protein < (target_protein_per_day / 3 * 0.8):
                        new_foods = self._retrieve_relevant_foods(goal, meal_type, int(day))
                        items.clear()
                        meal_kcal = 0
                        meal_protein = 0
                        for food in new_foods[:3]:
                            found = self._fuzzy_find(food)
                            if found and found in self.food_db:
                                base_kcal = self.food_db[found].get("kalori", 0)
                                base_protein = self.food_db[found].get("protein", 0.0)
                                base_karbo = self.food_db[found].get("karbo", 0.0)
                                base_lemak = self.food_db[found].get("lemak", 0.0)
                                if base_kcal == 0:
                                    logger.warning(f"Makanan {found} memiliki kalori 0, menggunakan porsi default 100g.")
                                    portion_g = 100
                                else:
                                    portion_g = max(100, (target_kcal_per_day / 3 / 3) / (base_kcal / 100))
                                portion_g = min(portion_g, 300)
                                kcal = (base_kcal * portion_g) / 100
                                protein = (base_protein * portion_g) / 100
                                karbo = (base_karbo * portion_g) / 100
                                lemak = (base_lemak * portion_g) / 100
                                if meal_kcal + kcal <= (target_kcal_per_day / 3 * 1.2):
                                    items.append({
                                        "name": f"{found} ({int(portion_g)}g)",
                                        "kalori": kcal,
                                        "protein": protein,
                                        "karbo": karbo,
                                        "lemak": lemak,
                                        "found": True
                                    })
                                    meal_kcal += kcal
                                    meal_protein += protein
                                    self.used_foods[int(day)].add(found)
            success, eval_result = self._validate_nutrition(plan, goal)
            self.trace.append({"plan": plan, "eval": eval_result})
        
        return {
            "final_report": plan,
            "eval": eval_result,
            "trace": self.trace
        }