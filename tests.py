import pytest
from agent import MealPlannerAgent

@pytest.fixture
def agent():
    """
    Fixture untuk agent dengan mock API dan DB kecil.
    """
    def mock_api(p, m):
        # Mock respons API JSON sederhana
        return '{"plan": {"1": {"sarapan": ["telur_rebus"]}}}'
    db = {"telur_rebus": {"kalori": 78, "protein": 6.0}}
    return MealPlannerAgent(mock_api, db)

def test_plan_once(agent):
    """
    Test generate plan sekali.
    """
    goal = {"days": 1}
    plan, _ = agent.plan_once(goal)
    assert "1" in plan
    assert "sarapan" in plan["1"]

def test_fuzzy_find(agent):
    """
    Test fuzzy matching.
    """
    assert agent._fuzzy_find("telur rebus") == "telur_rebus"  # Harus match meski spasi berbeda
    assert agent._fuzzy_find("item tidak ada") is None  # Harus None jika tidak ada

def test_evaluate(agent):
    """
    Test evaluasi dengan report mock.
    """
    report = {"1": {"total_kalori": 2000, "total_protein": 50, "meals": {}}}
    goal = {"target_kcal_per_day": 2000, "min_protein_per_day": 50}
    evaln = agent.evaluate(report, goal)
    assert evaln["success"] is True  # Harus success jika match target

# Tambah test lain jika perlu