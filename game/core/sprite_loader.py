"""
Sistema centralizado de pré-carregamento de sprites animados.
Carrega todos os sprites uma vez no início do jogo para evitar travamentos.
"""

from typing import Callable, Any

class SpriteLoader:
    """Gerenciador central de sprites animados."""
    
    _instance = None
    _loaded = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not SpriteLoader._loaded:
            self.loaders: list[tuple[str, Callable[[], Any]]] = []
    
    def register(self, name: str, loader_func: Callable[[], Any]) -> None: 
        """Registra uma função de carregamento de sprites."""
        if not SpriteLoader._loaded:
            self.loaders.append((name, loader_func))
    
    def load_all(self) -> None: 
        """Carrega todos os sprites registrados."""
        if SpriteLoader._loaded:
            return
        
        print("🎮 Carregando sprites animados...")
        for name, loader_func in self.loaders:
            print(f"  ⏳ Carregando {name}...")
            loader_func()
            print(f"  ✅ {name} carregado!")
        
        SpriteLoader._loaded = True
        print("✅ Todos os sprites carregados!\n")
    
    @classmethod
    def is_loaded(cls) -> bool:
        """Verifica se os sprites já foram carregados."""
        return cls._loaded

# Instância global
sprite_loader = SpriteLoader()
