# 🎯 Sistema de Mira Múltipla do Boss

## 📋 Funcionalidade Implementada

O boss agora exibe **linhas de mira múltiplas** durante o modo frenzy, mostrando exatamente onde cada um dos 3 lasers será disparado.

## 🎮 Comportamento

### **Modo Normal**
- **1 linha de mira** tracejada
- Aponta diretamente para o jogador
- Cor padrão da linha de mira

### **Modo Frenzy**
- **3 linhas de mira** tracejadas simultâneas
- Cada linha mostra a trajetória de um laser específico
- **Laser central**: Linha mais grossa e cor mais intensa
- **Lasers laterais**: Linhas mais finas e cor mais suave

## 🔧 Implementação Técnica

### **Métodos Adicionados:**

#### `_draw_single_aiming_line()`
```python
def _draw_single_aiming_line(surface, face_x, face_y, face_normal, time_based_offset)
```
- Desenha linha única para modo normal
- Mantém comportamento original

#### `_draw_frenzy_aiming_lines()`
```python
def _draw_frenzy_aiming_lines(surface, face_x, face_y, face_normal, time_based_offset)
```
- Desenha 3 linhas simultâneas para modo frenzy
- Cada linha corresponde exatamente à trajetória de um laser
- Calcula posições e ângulos usando `FRENZY_LASER_ANGLES`

### **Método Principal Modificado:**

#### `_draw_aiming_line()`
```python
def _draw_aiming_line(surface)
```
- Detecta automaticamente o modo (normal/frenzy)
- Chama o método apropriado para desenhar as linhas

## 🎨 Diferenciação Visual

| Laser | Cor | Espessura | Posição | Ordem de Desenho |
|-------|-----|-----------|---------|------------------|
| Lateral Esquerdo | 70% da cor original | 2px | Deslocado à esquerda | 1º (fundo) |
| Lateral Direito | 70% da cor original | 2px | Deslocado à direita | 2º (fundo) |
| Central | Cor original intensa | 3px | Centro do boss | 3º (topo) |

### **Ordem de Renderização:**
```python
draw_order = [0, 2, 1]  # Esquerdo, Direito, Centro
```
- **Lasers laterais** são desenhados primeiro (fundo)
- **Laser central** é desenhado por último (topo)
- **Resultado**: Laser central sempre visível e destacado

## 📐 Cálculos de Precisão

### **Posicionamento dos Lasers:**
1. **Face do boss**: Ponto de origem centralizado
2. **Offset lateral**: `(i - 1) * LASER_SPREAD_OFFSET` (-10, 0, +10)
3. **Rotação**: Cada laser rotacionado pelos ângulos em `FRENZY_LASER_ANGLES`
4. **Direção**: Calculada com rotação matricial para precisão máxima

### **Sincronização:**
- As linhas de mira mostram **exatamente** onde os lasers vão atingir
- Mesma lógica de cálculo usada para disparar os lasers reais
- Animação tracejada mantém o efeito visual dinâmico

## 🎯 Benefícios

1. **Feedback Visual Claro**: Jogador vê exatamente onde será atingido
2. **Previsibilidade**: Permite estratégia e esquiva mais precisa
3. **Profissionalismo**: Sistema polido e consistente
4. **Fairness**: Jogador tem informação suficiente para reagir

## 🔮 Experiência do Jogador

### **Antes:**
```
Boss em frenzy → Laser único visível → 3 lasers aparecem → Surpresa!
```

### **Agora:**
```
Boss em frenzy → 3 linhas de mira visíveis → 3 lasers nos locais previstos → Estratégia!
```

O sistema agora oferece uma experiência muito mais justa e estratégica para o jogador! 🎮✨