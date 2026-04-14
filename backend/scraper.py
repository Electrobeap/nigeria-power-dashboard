import random

def fetch_grid_data():
    try:
        # simulate realistic Nigerian grid range
        simulated_value = random.randint(3000, 5000)

        return {
            "total_generation_mw": simulated_value,
            "timestamp": "live",
            "source": "Simulated (stable system)"
        }

    except Exception as e:
        return {
            "total_generation_mw": 3500,
            "timestamp": "fallback",
            "source": "Fallback system"
        }