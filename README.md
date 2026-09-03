# Simulador de Acelerador de Partículas

Síncrotron / colisor circular interativo em Python (Pygame).

Dois feixes (próton e antipróton) circulam em sentidos opostos num anel com ímãs dipolares e cavidades de radiofrequência. A energia sobe a cada passagem pela RF. O campo magnético precisa acompanhar o momento das partículas — senão o feixe bate na parede da câmara de vácuo. Quando os feixes se cruzam nos pontos de interação (IP), há colisões.

## Como rodar

```bash
git clone https://github.com/f-soff/simulador-acelerador-particulas.git
cd simulador-acelerador-particulas
pip install -r requirements.txt
python acelerador.py
```

Requer Python 3.10+ e Pygame.

## Controles

| Tecla | Ação |
|---|---|
| `ESPAÇO` | Injeta os dois feixes e liga a RF |
| `↑` / `↓` | Aumenta / diminui a tensão das cavidades RF |
| `←` / `→` | Diminui / aumenta o campo B (desliga a rampa automática) |
| `A` | Liga / desliga a rampa automática de B (modo síncrotron) |
| `C` | Força uma colisão no ponto de interação |
| `P` | Pausa |
| `R` | Reinicia a máquina |
| `H` | Mostra / oculta a ajuda |
| `ESC` | Sai |

## O que o simulador está mostrando

- **Ímãs dipolares** (setores cobreados): campo **B** perpendicular ao plano. A força de Lorentz \( \mathbf{F} = q\,\mathbf{v}\times\mathbf{B} \) curva a trajetória.
- **Cavidades RF** (blocos roxos): campo elétrico tangencial que incrementa a energia a cada volta.
- **Câmara de vácuo**: se o raio de curvatura \( R = p/(qB) \) não coincidir com o raio do anel, a partícula se perde.
- **Rampa automática de B**: como num síncrotron real, B cresce junto com o momento para manter a órbita fixa.
- **Relatividade**: \( \beta = v/c = \sqrt{1 - (mc^2/E)^2} \). Perto do teto de energia a velocidade quase não muda — o que cresce é \( \gamma \).
- **Colisões**: quando os feixes se cruzam nos IPs com energia suficiente, o simulador gera um jato de fragmentos (puramente visual).

## Números didáticos (não é o LHC)

O anel tem 100 m de raio (o LHC tem ~4,3 km). A injeção é em 8 GeV e o teto em 450 GeV. Os valores de B são consistentes com \( B\rho \approx p[\mathrm{GeV}/c] / 0.3 \) em T·m.

Experimento sugerido: desligue a rampa (`A`) depois que o feixe estiver estável e mexa em B com as setas. Veja o feixe espiralar para fora (B baixo) ou para dentro (B alto).
