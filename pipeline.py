"""
pipeline.py
-----------
Runs the full Running Performance Analytics pipeline end-to-end.

  Step 1  src/clean_strava.py   Load, filter, convert units, clean
  Step 2  src/features.py       Rolling load features + effort labels
  Step 3  src/model.py          Ridge regression pace model (≥ 20 runs)
  Step 4  src/visualize.py      Generate all training figures

Usage:
    python pipeline.py

Run individual steps directly if you only need to regenerate part of it:
    python src/clean_strava.py
    python src/features.py
    python src/model.py
    python src/visualize.py
"""
import sys
from pathlib import Path

# Make src/ importable without installing the package
sys.path.insert(0, str(Path(__file__).parent / "src"))

from clean_strava  import main as step_clean
from fetch_weather import main as step_weather
from features      import main as step_features
from model         import main as step_model
from visualize     import main as step_visualize

DIVIDER = "─" * 54


def run() -> None:
    print(f"\n{'=' * 54}")
    print(f"  Running Performance Analytics — Pipeline")
    print(f"{'=' * 54}\n")

    steps = [
        ("Clean data",         step_clean),
        ("Fetch weather",      step_weather),
        ("Engineer features",  step_features),
        ("Train model",        step_model),
        ("Generate figures",   step_visualize),
    ]
    for label, fn in steps:
        print(DIVIDER)
        fn()
        print()

    print(DIVIDER)
    print("  Pipeline complete!")
    print(f"  → Figures  : figures/")
    print(f"  → Clean data: data/clean/")
    print(DIVIDER + "\n")


if __name__ == "__main__":
    run()
