#!/usr/bin/env python3
"""
Simulador de Acelerador de Partículas
=====================================
Síncrotron / colisor circular 2D com:
  - dois feixes em sentidos opostos
  - campo magnético dipolar (curva a trajetória)
  - cavidades de RF (aceleram as partículas)
  - cinemática relativística
  - perda de feixe se B estiver errado
  - colisão no ponto de interação

Controles:
  ESPAÇO     injetar / ligar RF
  ↑ / ↓      tensão das cavidades RF
  ← / →      campo magnético B
  A          rampa automática de B (síncrotron)
  C          forçar colisão
  R          reiniciar
  P          pausar
  H          mostrar / ocultar ajuda
  ESC        sair
"""

from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass, field

import pygame


# ---------------------------------------------------------------------------
# Constantes físicas (SI) e unidades de visualização
# ---------------------------------------------------------------------------
C = 299_792_458.0          # m/s
E_CHARGE = 1.602176634e-19  # C
M_PROTON = 1.6726219e-27    # kg
REST_ENERGY_PROTON_GEV = 0.938272  # GeV

# Escala do anel na tela ↔ "mundo"
RING_RADIUS_M = 100.0       # raio físico fictício (m) — anel didático
INJECTION_GEV = 8.0         # energia de injeção
MAX_ENERGY_GEV = 450.0      # teto do síncrotron didático
RF_KICK_GEV = 6.0           # incremento por passagem em cada cavidade (didático)
VISUAL_C = 780.0            # velocidade visual (px/s) quando β → 1


def beta_from_energy(energy_gev: float, rest_gev: float = REST_ENERGY_PROTON_GEV) -> float:
    """v/c a partir da energia total E."""
    gamma = max(energy_gev / rest_gev, 1.0000001)
    return math.sqrt(max(0.0, 1.0 - 1.0 / (gamma * gamma)))


def momentum_gev_c(energy_gev: float, rest_gev: float = REST_ENERGY_PROTON_GEV) -> float:
    """Momento em GeV/c."""
    return math.sqrt(max(0.0, energy_gev * energy_gev - rest_gev * rest_gev))


def rigidity_tesla_meter(energy_gev: float) -> float:
    """Bρ ≈ p / 0.2998  (T·m) para carga |q|=e."""
    return momentum_gev_c(energy_gev) / 0.299792458


def required_b(energy_gev: float, radius_m: float = RING_RADIUS_M) -> float:
    """Campo B (T) que mantém a órbita de raio R."""
    return rigidity_tesla_meter(energy_gev) / radius_m


# ---------------------------------------------------------------------------
# Partícula
# ---------------------------------------------------------------------------
@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    energy: float
    charge: float          # +1 ou -1 (em unidades de e)
    rest: float = REST_ENERGY_PROTON_GEV
    alive: bool = True
    trail: list = field(default_factory=list)
    hue_shift: float = 0.0
    collision_child: bool = False
    life: float = 1.0      # para fragmentos de colisão

    @property
    def gamma(self) -> float:
        return max(self.energy / self.rest, 1.0)

    @property
    def beta(self) -> float:
        return beta_from_energy(self.energy, self.rest)

    @property
    def speed(self) -> float:
        return self.beta * C


# ---------------------------------------------------------------------------
# Acelerador
# ---------------------------------------------------------------------------
class Accelerator:
    def __init__(self, width: int, height: int) -> None:
        self.w = width
        self.h = height
        self.cx = width * 0.42
        self.cy = height * 0.52

        # Geometria em pixels
        self.r_pix = min(width, height) * 0.36
        self.pipe_half = 26.0          # meia-largura do tubo (px)
        self.scale = self.r_pix / RING_RADIUS_M  # px / m

        # Estado da máquina
        self.B = required_b(INJECTION_GEV)   # Tesla
        self.rf_voltage = 1.0                # multiplicador da cavidade
        self.auto_ramp = True
        self.rf_on = False
        self.paused = False
        self.help_on = True
        self.time = 0.0
        self.revolutions = 0.0
        self.collisions = 0
        self.max_energy_seen = INJECTION_GEV
        self.flash = 0.0
        self.status = "Pronto para injetar. Pressione ESPAÇO."

        # Cavidades RF em θ = 0 e θ = π
        self.rf_angles = (0.0, math.pi)
        self.rf_width = 0.12  # rad

        # Ímãs dipolares: 8 setores
        self.n_dipoles = 8
        self.dipole_frac = 0.72  # fração do setor ocupada pelo dipolo

        self.beam1: list[Particle] = []
        self.beam2: list[Particle] = []
        self.debris: list[Particle] = []

        self._rf_latched = set()

    # -- injeção ----------------------------------------------------------
    def inject(self, n_per_beam: int = 14) -> None:
        self.beam1.clear()
        self.beam2.clear()
        self.debris.clear()
        self.rf_on = True
        self.revolutions = 0.0
        self.collisions = 0
        self.max_energy_seen = INJECTION_GEV
        self.B = required_b(INJECTION_GEV)
        self.status = "Feixes injetados. RF ligada. Rampa de B automática."

        for i in range(n_per_beam):
            dtheta = (i - n_per_beam / 2) * 0.010
            dE = random.uniform(-0.12, 0.12)
            self.beam1.append(self._spawn(+1, -math.pi / 2 + dtheta, INJECTION_GEV + dE, +1))
            self.beam2.append(self._spawn(-1, -math.pi / 2 + dtheta, INJECTION_GEV + dE, -1))

    def _spawn(self, direction: int, theta: float, energy: float, charge: float) -> Particle:
        x = self.cx + self.r_pix * math.cos(theta)
        y = self.cy + self.r_pix * math.sin(theta)
        beta = beta_from_energy(energy)
        v_vis = VISUAL_C * beta
        tx = -math.sin(theta) * direction
        ty = math.cos(theta) * direction
        return Particle(
            x=x, y=y,
            vx=tx * v_vis, vy=ty * v_vis,
            energy=energy, charge=charge,
            hue_shift=random.uniform(-0.08, 0.08),
        )

    def step(self, dt: float) -> None:
        if self.paused:
            return
        self.time += dt
        if self.flash > 0:
            self.flash = max(0.0, self.flash - dt * 2.5)

        if self.rf_on:
            self._rf_kick_bunches()

        if self.auto_ramp and (self.beam1 or self.beam2):
            e_avg = self.average_energy()
            target = required_b(e_avg)
            self.B += (target - self.B) * min(1.0, dt * 18.0)

        self._integrate(self.beam1, +1, dt)
        self._integrate(self.beam2, -1, dt)
        self._integrate_debris(dt)
        self._check_collisions()

        if self.beam1 or self.beam2:
            self.max_energy_seen = max(self.max_energy_seen, self.average_energy())
            beta = beta_from_energy(self.average_energy())
            omega = (VISUAL_C * beta) / self.r_pix
            self.revolutions += omega * dt / (2 * math.pi)

    def _integrate(self, beam: list[Particle], direction: int, dt: float) -> None:
        survivors: list[Particle] = []
        for p in beam:
            if not p.alive:
                continue
            self._push(p, direction, dt)
            dx, dy = p.x - self.cx, p.y - self.cy
            r = math.hypot(dx, dy)
            if abs(r - self.r_pix) > self.pipe_half + 4:
                p.alive = False
                continue
            p.trail.append((p.x, p.y))
            if len(p.trail) > 28:
                p.trail.pop(0)
            survivors.append(p)
        beam[:] = survivors

    def _push(self, p: Particle, direction: int, dt: float) -> None:
        dx, dy = p.x - self.cx, p.y - self.cy
        r = max(math.hypot(dx, dy), 1.0)
        theta = math.atan2(dy, dx)

        B_eff = max(self.B, 1e-9)
        B_req = max(required_b(p.energy), 1e-9)

        v = VISUAL_C * p.beta
        omega = direction * v / r

        r_eq = self.r_pix * (B_req / max(B_eff, 1e-9))
        r += (r_eq - r) * min(1.0, dt * 3.5)

        theta += omega * dt
        p.x = self.cx + r * math.cos(theta)
        p.y = self.cy + r * math.sin(theta)
        p.vx = -math.sin(theta) * direction * v
        p.vy = math.cos(theta) * direction * v

    def _bunch_theta(self, beam: list[Particle]):
        if not beam:
            return None
        sx = sum((p.x - self.cx) for p in beam)
        sy = sum((p.y - self.cy) for p in beam)
        return math.atan2(sy, sx)

    def _rf_kick_bunches(self) -> None:
        for beam_id, beam in (("b1", self.beam1), ("b2", self.beam2)):
            th = self._bunch_theta(beam)
            if th is None:
                continue
            inside = self._in_rf(th)
            key = beam_id
            if inside and key not in self._rf_latched:
                kick = RF_KICK_GEV * self.rf_voltage
                for p in beam:
                    p.energy = min(MAX_ENERGY_GEV, max(p.rest * 1.01, p.energy + kick))
                self._rf_latched.add(key)
            elif not inside:
                self._rf_latched.discard(key)

    def _in_dipole(self, theta: float) -> bool:
        sector = 2 * math.pi / self.n_dipoles
        phase = (theta + 2 * math.pi) % sector
        return phase < sector * self.dipole_frac

    def _in_rf(self, theta: float) -> bool:
        t = (theta + 2 * math.pi) % (2 * math.pi)
        for a in self.rf_angles:
            d = abs((t - a + math.pi) % (2 * math.pi) - math.pi)
            if d < self.rf_width:
                return True
        return False

    def _integrate_debris(self, dt: float) -> None:
        keep: list[Particle] = []
        for p in self.debris:
            p.life -= dt * 0.85
            if p.life <= 0:
                continue
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.985
            p.vy *= 0.985
            p.trail.append((p.x, p.y))
            if len(p.trail) > 16:
                p.trail.pop(0)
            keep.append(p)
        self.debris = keep

    def _check_collisions(self) -> None:
        if not self.beam1 or not self.beam2:
            return
        if self.average_energy() < 40:
            return

        ips = (
            (-math.pi / 2, self.cx, self.cy - self.r_pix),
            (math.pi / 2, self.cx, self.cy + self.r_pix),
        )
        ang_win = 0.10
        for th_ip, ipx, ipy in ips:
            def near(p, th_ip=th_ip):
                th = math.atan2(p.y - self.cy, p.x - self.cx)
                d = abs((th - th_ip + math.pi) % (2 * math.pi) - math.pi)
                return d < ang_win
            near1 = [p for p in self.beam1 if near(p)]
            near2 = [p for p in self.beam2 if near(p)]
            if near1 and near2 and random.random() < 0.12:
                self._explode(ipx, ipy, (near1[0].energy + near2[0].energy))
                self.collisions += 1
                self.flash = 1.0
                e_cm = near1[0].energy + near2[0].energy
                self.status = f"Colisão #{self.collisions}  •  √s ≈ {e_cm:.1f} GeV"

    def _explode(self, x: float, y: float, e_cm: float) -> None:
        n = random.randint(18, 32)
        for _ in range(n):
            ang = random.uniform(0, 2 * math.pi)
            spd = random.uniform(80, 380)
            self.debris.append(
                Particle(
                    x=x, y=y,
                    vx=math.cos(ang) * spd,
                    vy=math.sin(ang) * spd,
                    energy=e_cm / n,
                    charge=random.choice((-1, 0, 1)),
                    trail=[],
                    collision_child=True,
                    life=random.uniform(0.7, 1.6),
                    hue_shift=random.uniform(0, 1),
                )
            )

    def force_collision(self) -> None:
        if not (self.beam1 and self.beam2):
            self.status = "Injete os feixes primeiro (ESPAÇO)."
            return
        self._explode(self.cx, self.cy - self.r_pix, self.average_energy() * 2)
        self.collisions += 1
        self.flash = 1.0
        self.status = f"Colisão forçada  •  √s ≈ {self.average_energy()*2:.1f} GeV"

    def average_energy(self) -> float:
        parts = self.beam1 + self.beam2
        if not parts:
            return INJECTION_GEV
        return sum(p.energy for p in parts) / len(parts)

    def alive_count(self):
        return len(self.beam1), len(self.beam2)

    def reset(self) -> None:
        self.beam1.clear()
        self.beam2.clear()
        self.debris.clear()
        self.rf_on = False
        self.B = required_b(INJECTION_GEV)
        self.rf_voltage = 1.0
        self.auto_ramp = True
        self.revolutions = 0.0
        self.collisions = 0
        self.flash = 0.0
        self.status = "Máquina reiniciada. Pressione ESPAÇO para injetar."


class Colors:
    BG = (8, 10, 18)
    PANEL = (14, 16, 28)
    PANEL_EDGE = (40, 48, 72)
    TEXT = (220, 228, 240)
    MUTED = (130, 140, 160)
    ACCENT = (90, 200, 255)
    GOLD = (255, 196, 72)
    MAGNET = (196, 92, 36)
    MAGNET_DIM = (90, 42, 18)
    CHAMBER = (36, 44, 64)
    CHAMBER_GLOW = (50, 70, 110)
    RF = (168, 92, 255)
    BEAM1 = (0, 210, 255)
    BEAM2 = (255, 70, 110)
    GOOD = (80, 220, 140)
    WARN = (255, 170, 60)
    BAD = (255, 80, 80)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def color_lerp(c1, c2, t: float):
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


class Renderer:
    def __init__(self, screen, font, font_sm, font_lg, font_tiny) -> None:
        self.s = screen
        self.font = font
        self.font_sm = font_sm
        self.font_lg = font_lg
        self.font_tiny = font_tiny
        self.w, self.h = screen.get_size()

    def draw(self, acc: Accelerator) -> None:
        self.s.fill(Colors.BG)
        self._stars()
        self._ring(acc)
        self._dipoles(acc)
        self._rf(acc)
        self._ips(acc)
        self._particles(acc)
        self._flash(acc)
        self._panel(acc)
        self._hud(acc)
        if acc.help_on:
            self._help()

    def _stars(self) -> None:
        rng = random.Random(42)
        for _ in range(90):
            x, y = rng.randint(0, self.w), rng.randint(0, self.h)
            c = rng.randint(30, 90)
            self.s.set_at((x, y), (c, c, c + 15))

    def _ring(self, acc: Accelerator) -> None:
        cx, cy, r = int(acc.cx), int(acc.cy), int(acc.r_pix)
        pygame.draw.circle(self.s, Colors.CHAMBER_GLOW, (cx, cy), r + int(acc.pipe_half) + 6, 3)
        pygame.draw.circle(self.s, Colors.CHAMBER, (cx, cy), r + int(acc.pipe_half), 5)
        pygame.draw.circle(self.s, Colors.CHAMBER, (cx, cy), r - int(acc.pipe_half), 5)
        pygame.draw.circle(self.s, (28, 36, 58), (cx, cy), r, 1)

    def _dipoles(self, acc: Accelerator) -> None:
        cx, cy, r = acc.cx, acc.cy, acc.r_pix
        sector = 2 * math.pi / acc.n_dipoles
        for i in range(acc.n_dipoles):
            a0 = i * sector
            a1 = a0 + sector * acc.dipole_frac
            self._arc(cx, cy, r, a0, a1, Colors.MAGNET, 11)
            for a in (a0, a1):
                x = int(cx + r * math.cos(a))
                y = int(cy + r * math.sin(a))
                pygame.draw.circle(self.s, Colors.MAGNET_DIM, (x, y), 6)

    def _arc(self, cx, cy, r, a0, a1, color, width) -> None:
        n = max(8, int(abs(a1 - a0) * r / 6))
        pts = []
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        if len(pts) >= 2:
            pygame.draw.lines(self.s, color, False, pts, width)

    def _rf(self, acc: Accelerator) -> None:
        pulse = 0.5 + 0.5 * math.sin(acc.time * 14)
        col = color_lerp((60, 30, 90), Colors.RF, pulse if acc.rf_on else 0.15)
        for a in acc.rf_angles:
            x = int(acc.cx + acc.r_pix * math.cos(a))
            y = int(acc.cy + acc.r_pix * math.sin(a))
            pygame.draw.rect(self.s, col, (x - 10, y - 16, 20, 32), border_radius=3)
            pygame.draw.rect(self.s, (240, 230, 255), (x - 10, y - 16, 20, 32), 1, border_radius=3)
            label = self.font_tiny.render("RF", True, (240, 230, 255))
            self.s.blit(label, (x - label.get_width() // 2, y - 28))

    def _ips(self, acc: Accelerator) -> None:
        for (x, y, name) in (
            (acc.cx, acc.cy - acc.r_pix, "IP-1"),
            (acc.cx, acc.cy + acc.r_pix, "IP-2"),
        ):
            pygame.draw.circle(self.s, (80, 70, 30), (int(x), int(y)), 10, 1)
            lab = self.font_tiny.render(name, True, Colors.GOLD)
            self.s.blit(lab, (int(x) + 12, int(y) - 6))

    def _particles(self, acc: Accelerator) -> None:
        self._draw_beam(acc.beam1, Colors.BEAM1)
        self._draw_beam(acc.beam2, Colors.BEAM2)
        for p in acc.debris:
            alpha = max(0.0, min(1.0, p.life))
            col = (
                int(255 * alpha),
                int((180 + 70 * p.hue_shift) * alpha),
                int(60 * alpha),
            )
            if len(p.trail) >= 2:
                pygame.draw.lines(self.s, col, False, p.trail, 1)
            pygame.draw.circle(self.s, col, (int(p.x), int(p.y)), 2)

    def _draw_beam(self, beam, color) -> None:
        for p in beam:
            if len(p.trail) >= 2:
                fade = color_lerp(Colors.BG, color, 0.45)
                pygame.draw.lines(self.s, fade, False, p.trail, 2)
            pygame.draw.circle(self.s, color, (int(p.x), int(p.y)), 4)
            pygame.draw.circle(self.s, (255, 255, 255), (int(p.x), int(p.y)), 2)

    def _flash(self, acc: Accelerator) -> None:
        if acc.flash <= 0:
            return
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        a = int(90 * acc.flash)
        overlay.fill((255, 230, 160, a))
        self.s.blit(overlay, (0, 0))

    def _panel(self, acc: Accelerator) -> None:
        px, pw = self.w - 360, 348
        rect = pygame.Rect(px, 16, pw, self.h - 32)
        pygame.draw.rect(self.s, Colors.PANEL, rect, border_radius=10)
        pygame.draw.rect(self.s, Colors.PANEL_EDGE, rect, 1, border_radius=10)

        x = px + 18
        y = 28
        title = self.font_lg.render("SÍNCROTRON", True, Colors.ACCENT)
        self.s.blit(title, (x, y))
        y += 34
        sub = self.font_sm.render("colisor circular didático", True, Colors.MUTED)
        self.s.blit(sub, (x, y))
        y += 28
        pygame.draw.line(self.s, Colors.PANEL_EDGE, (x, y), (px + pw - 18, y), 1)
        y += 16

        e = acc.average_energy()
        b1, b2 = acc.alive_count()
        beta = beta_from_energy(e)
        gamma = e / REST_ENERGY_PROTON_GEV
        b_req = required_b(e)
        mismatch = (acc.B - b_req) / max(b_req, 1e-9)

        rows = [
            ("Energia / feixe", f"{e:7.2f} GeV", Colors.GOLD),
            ("Energia no CM  √s", f"{2*e:7.2f} GeV", Colors.GOLD),
            ("γ  (fator Lorentz)", f"{gamma:7.2f}", Colors.TEXT),
            ("β  = v/c", f"{beta:7.6f}", Colors.TEXT),
            ("1 − β", f"{1-beta:.3e}", Colors.MUTED),
            ("Campo B", f"{acc.B:7.4f} T", Colors.ACCENT),
            ("B órbita ideal", f"{b_req:7.4f} T", Colors.MUTED),
            ("Erro de B", f"{mismatch*100:+6.2f} %", Colors.GOOD if abs(mismatch) < 0.08 else Colors.WARN if abs(mismatch) < 0.2 else Colors.BAD),
            ("Tensão RF", f"{acc.rf_voltage:6.2f} ×", Colors.RF),
            ("RF", "LIGADA" if acc.rf_on else "desligada", Colors.GOOD if acc.rf_on else Colors.MUTED),
            ("Rampa auto de B", "ON" if acc.auto_ramp else "OFF", Colors.GOOD if acc.auto_ramp else Colors.WARN),
            ("Voltas", f"{acc.revolutions:8.1f}", Colors.TEXT),
            ("Feixe +  /  Feixe −", f"{b1:3d}   /  {b2:3d}", Colors.TEXT),
            ("Colisões", f"{acc.collisions}", Colors.GOLD),
        ]
        for label, value, col in rows:
            self.s.blit(self.font_sm.render(label, True, Colors.MUTED), (x, y))
            self.s.blit(self.font_sm.render(value, True, col), (x + 168, y))
            y += 22

        y += 8
        self.s.blit(self.font_tiny.render("ENERGIA DO FEIXE", True, Colors.MUTED), (x, y))
        y += 16
        bar = pygame.Rect(x, y, pw - 36, 12)
        pygame.draw.rect(self.s, (24, 28, 40), bar, border_radius=4)
        frac = max(0.0, min(1.0, (e - INJECTION_GEV) / (MAX_ENERGY_GEV - INJECTION_GEV)))
        fill = pygame.Rect(x, y, int((pw - 36) * frac), 12)
        pygame.draw.rect(self.s, color_lerp(Colors.BEAM1, Colors.GOLD, frac), fill, border_radius=4)
        y += 28

        self.s.blit(self.font_tiny.render("CASAMENTO B ↔ p  (órbita)", True, Colors.MUTED), (x, y))
        y += 16
        bar = pygame.Rect(x, y, pw - 36, 10)
        pygame.draw.rect(self.s, (24, 28, 40), bar, border_radius=4)
        mid = x + (pw - 36) // 2
        pygame.draw.line(self.s, Colors.MUTED, (mid, y - 2), (mid, y + 12), 1)
        needle = mid + int(max(-1, min(1, mismatch * 3)) * (pw - 48) / 2)
        pygame.draw.circle(self.s, Colors.GOLD, (needle, y + 5), 6)
        y += 26

        self._blit_wrap(acc.status, x, y, pw - 36, Colors.ACCENT)

    def _blit_wrap(self, text: str, x: int, y: int, max_w: int, color) -> None:
        words = text.split()
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if self.font_sm.size(test)[0] <= max_w:
                line = test
            else:
                self.s.blit(self.font_sm.render(line, True, color), (x, y))
                y += 18
                line = w
        if line:
            self.s.blit(self.font_sm.render(line, True, color), (x, y))

    def _hud(self, acc: Accelerator) -> None:
        title = self.font.render("ACELERADOR DE PARTÍCULAS", True, Colors.TEXT)
        self.s.blit(title, (24, 16))
        hint = self.font_tiny.render("H mostra / oculta os controles", True, Colors.MUTED)
        self.s.blit(hint, (24, 42))
        if acc.paused:
            p = self.font_lg.render("PAUSADO", True, Colors.WARN)
            self.s.blit(p, (24, self.h - 48))

    def _help(self) -> None:
        lines = [
            "ESPAÇO   injetar feixes / ligar RF",
            "↑ ↓      tensão das cavidades RF",
            "← →      campo magnético B",
            "A        rampa automática de B",
            "C        forçar colisão no IP",
            "P        pausar",
            "R        reiniciar a máquina",
            "H        ocultar esta ajuda",
            "ESC      sair",
        ]
        box_h = 22 * len(lines) + 16
        rect = pygame.Rect(20, self.h - box_h - 20, 340, box_h)
        pygame.draw.rect(self.s, Colors.PANEL, rect, border_radius=8)
        pygame.draw.rect(self.s, Colors.PANEL_EDGE, rect, 1, border_radius=8)
        for i, line in enumerate(lines):
            self.s.blit(self.font_tiny.render(line, True, Colors.TEXT), (34, rect.y + 10 + i * 22))


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Simulador de Acelerador de Partículas")
    flags = pygame.RESIZABLE
    screen = pygame.display.set_mode((1280, 740), flags)
    clock = pygame.time.Clock()

    def fonts():
        return (
            pygame.font.SysFont("consolas,dejavusansmono,monospace", 22),
            pygame.font.SysFont("consolas,dejavusansmono,monospace", 16),
            pygame.font.SysFont("consolas,dejavusansmono,monospace", 26, bold=True),
            pygame.font.SysFont("consolas,dejavusansmono,monospace", 13),
        )

    font, font_sm, font_lg, font_tiny = fonts()
    acc = Accelerator(*screen.get_size())
    renderer = Renderer(screen, font, font_sm, font_lg, font_tiny)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        dt = min(dt, 0.05)

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((ev.w, ev.h), flags)
                acc = Accelerator(ev.w, ev.h)
                renderer = Renderer(screen, font, font_sm, font_lg, font_tiny)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_SPACE:
                    acc.inject()
                elif ev.key == pygame.K_r:
                    acc.reset()
                elif ev.key == pygame.K_p:
                    acc.paused = not acc.paused
                elif ev.key == pygame.K_h:
                    acc.help_on = not acc.help_on
                elif ev.key == pygame.K_a:
                    acc.auto_ramp = not acc.auto_ramp
                    acc.status = "Rampa automática de B " + ("ligada." if acc.auto_ramp else "desligada. Ajuste B manualmente.")
                elif ev.key == pygame.K_c:
                    acc.force_collision()
                elif ev.key == pygame.K_UP:
                    acc.rf_voltage = min(4.0, acc.rf_voltage + 0.1)
                elif ev.key == pygame.K_DOWN:
                    acc.rf_voltage = max(0.0, acc.rf_voltage - 0.1)
                elif ev.key == pygame.K_RIGHT:
                    acc.auto_ramp = False
                    acc.B *= 1.06
                elif ev.key == pygame.K_LEFT:
                    acc.auto_ramp = False
                    acc.B /= 1.06

        acc.step(dt)
        renderer.draw(acc)
        fps_s = font_tiny.render(f"{clock.get_fps():4.0f} fps", True, Colors.MUTED)
        screen.blit(fps_s, (24, 60))
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)
