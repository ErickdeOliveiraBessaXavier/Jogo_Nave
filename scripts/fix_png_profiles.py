"""Strip incorrect iCCP profiles from PNG files under `game/assets`.

Usage:
  python scripts/fix_png_profiles.py

It finds the repo root (a parent that contains `game/`) then scans `game/assets` recursively.
"""

from pathlib import Path

from PIL import Image


def find_repo_root_with_game(start: Path) -> Path | None:
    p = start.resolve()
    if (p / "game").exists():
        return p
    for parent in p.parents:
        if (parent / "game").exists():
            return parent
    return None


def fix_png_profile(png_path: Path) -> bool:
    try:
        img = Image.open(png_path)
        # If there's an icc_profile, remove it and re-save
        icc = img.info.pop("icc_profile", None)
        if icc is None:
            return False
        img.save(png_path, format="PNG", optimize=True)
        return True
    except Exception as e:
        print(f"Error processing {png_path}: {e}")
        return False


def main() -> None:
    start = Path(__file__).parent
    repo_root = find_repo_root_with_game(start)
    if repo_root is None:
        print("Could not locate project root containing `game/` directory.")
        return

    assets_dir = repo_root / "game" / "assets"
    if not assets_dir.exists():
        print(f"Assets directory not found: {assets_dir}")
        return

    png_files = list(assets_dir.rglob("*.png"))
    print(f"Found {len(png_files)} PNG files under {assets_dir}")

    fixed = 0
    for p in png_files:
        if fix_png_profile(p):
            print(f"✓ Fixed: {p.relative_to(repo_root)}")
            fixed += 1

    print(f"\nDone. Stripped iCCP profile from {fixed}/{len(png_files)} files.")


if __name__ == "__main__":
    main()
