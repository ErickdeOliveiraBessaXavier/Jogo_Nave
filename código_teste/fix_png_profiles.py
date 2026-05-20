"""Script para remover perfis iCCP incorretos de imagens PNG."""

from pathlib import Path

from PIL import Image


def fix_png_profile(png_path: Path):
    """Remove o perfil iCCP de uma imagem PNG."""
    try:
        img = Image.open(png_path)

        # Remover informações iCCP
        if "icc_profile" in img.info:
            del img.info["icc_profile"]

        # Salvar sem o perfil
        img.save(png_path, "PNG", optimize=True)
        print(f"✓ Corrigido: {png_path.name}")
        return True
    except Exception as e:
        print(f"✗ Erro ao processar {png_path.name}: {e}")
        return False


def main():
    """Processa todas as imagens PNG no diretório de assets."""
    base_dir = Path(__file__).parent.parent / "game" / "assets"

    if not base_dir.exists():
        print(f"Diretório não encontrado: {base_dir}")
        return

    # Encontrar todas as imagens PNG em todos os subdiretórios de assets
    png_files = list(base_dir.rglob("*.png"))

    print(f"Encontradas {len(png_files)} imagens PNG")
    print("Processando...\n")

    success_count = 0
    for png_file in png_files:
        if fix_png_profile(png_file):
            success_count += 1

    print(f"\n{success_count}/{len(png_files)} imagens processadas com sucesso!")


if __name__ == "__main__":
    main()
