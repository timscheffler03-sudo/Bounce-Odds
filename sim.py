"""Bounce Odds – 6 Arenen mit Flummi-Physik. Komplett berechnet, keine KI nötig.

  python3 sim.py --mode ring --seed 3 --out video.mp4     # Video rendern
  python3 sim.py --mode ring --seed 3 --dry               # nur Physik (schnell), gibt Kennzahlen aus
Modi: ring, rings, plinko, versus, hexagon, cup
"""
import argparse, json, math, random, subprocess, wave
import numpy as np
import cairo
from engine import substep

W, H, FPS, SUB = 1080, 1920, 30, 6
CX, CY = 540.0, 1000.0
MAXN = 2600
TRAIL = 6
FONT = 'DejaVu Sans'

PALETTES = [
    [(0.98, 0.42, 0.42), (0.99, 0.75, 0.30), (0.40, 0.88, 0.62), (0.35, 0.65, 0.98), (0.80, 0.55, 0.98)],
    [(1.0, 0.50, 0.70), (1.0, 0.85, 0.40), (0.45, 0.95, 0.90), (0.55, 0.65, 1.0), (0.95, 0.60, 0.40)],
    [(0.30, 0.95, 0.95), (0.55, 0.60, 1.0), (0.95, 0.45, 0.95), (1.0, 0.85, 0.35), (0.50, 1.0, 0.60)],
]
RED, BLUE = (0.98, 0.38, 0.38), (0.33, 0.62, 1.0)


# ------------------------------------------------------------------ Welt
class World:
    def __init__(self):
        self.x = np.zeros(MAXN); self.y = np.zeros(MAXN); self.vx = np.zeros(MAXN); self.vy = np.zeros(MAXN)
        self.rad = np.ones(MAXN) * 10; self.alive = np.zeros(MAXN, np.bool_); self.hit = np.zeros(MAXN, np.int64)
        self.team = np.zeros(MAXN, np.int64); self.col = np.zeros(MAXN, np.int64); self.cool = np.zeros(MAXN)
        self.tx = np.zeros((MAXN, TRAIL)); self.ty = np.zeros((MAXN, TRAIL))
        self.n = 0
        self.conv = np.zeros((256, 2), np.int64)

    def spawn(self, x, y, vx, vy, r, col=0, team=0, cool=0.0):
        if self.n >= MAXN - 1:
            return -1
        i = self.n
        self.x[i], self.y[i], self.vx[i], self.vy[i], self.rad[i] = x, y, vx, vy, r
        self.alive[i] = True; self.hit[i] = 0; self.team[i] = team; self.col[i] = col; self.cool[i] = cool
        self.tx[i, :] = x; self.ty[i, :] = y
        self.n += 1
        return i

    def split(self, i, rng, spread=1.2):
        rot = rng.uniform(-spread, spread)
        c, s = math.cos(rot), math.sin(rot)
        vx, vy = self.vx[i], self.vy[i]
        return self.spawn(self.x[i] + rng.uniform(-2, 2), self.y[i] + rng.uniform(-2, 2), vx * c - vy * s, vx * s + vy * c,
                          self.rad[i], (self.col[i] + 1) % 5, self.team[i], 0.5)

    def compact(self):
        m = self.alive[:self.n].copy()
        if m.all():
            return
        k = int(m.sum())
        for a in (self.x, self.y, self.vx, self.vy, self.rad, self.alive, self.hit, self.team, self.col, self.cool):
            a[:k] = a[:self.n][m]
        self.tx[:k] = self.tx[:self.n][m]; self.ty[:k] = self.ty[:self.n][m]
        self.n = k


def seg_arr(segs):
    a = np.zeros((max(1, len(segs)), 8))
    for k, s in enumerate(segs):
        a[k, :len(s)] = s
    return a, len(segs)


def ring_arr(rings):
    a = np.zeros((max(1, len(rings)), 6))
    for k, r in enumerate(rings):
        a[k] = r
    return a, len(rings)


def fmt(v):
    return f"{int(v):,}"


# ------------------------------------------------------------------ Modi
class Mode:
    gravity = 900.0
    rest = 1.0
    ball_ball = True
    vmin, vmax = 0.0, 2600.0
    maxdur = 55.0

    def __init__(self, rng):
        self.rng = rng
        self.pal = rng.choice(PALETTES)
        self.outcome = None
        self.t = 0.0
        self.hist = []
        self.events = []

    # Kollisionsobjekte für Zeitpunkt t
    def colliders(self, t):
        return [], [], []

    def speed_clamp(self, w):
        if self.vmin <= 0 and self.vmax >= 2600:
            return
        n = w.n
        v = np.hypot(w.vx[:n], w.vy[:n]) + 1e-9
        f = np.ones(n)
        lo = v < self.vmin; hi = v > self.vmax
        f[lo] = self.vmin / v[lo]; f[hi] = self.vmax / v[hi]
        w.vx[:n] *= f; w.vy[:n] *= f

    def ev(self, kind, val=0.0):
        self.events.append((kind, val))


class RingMode(Mode):
    """1 Flummi-Ring: jeder kräftige Abprall teilt, die Lücke dreht sich."""
    name = 'ring'
    gravity = 900.0
    vmin, vmax = 520.0, 1500.0

    def __init__(self, rng):
        super().__init__(rng)
        self.R = 470.0
        self.target = rng.choice([750, 1000, 1000, 1200])
        self.gap = math.radians(rng.uniform(13, 20))
        self.gw = rng.choice([-1, 1]) * rng.uniform(0.6, 1.0)
        self.ga0 = -math.pi / 2 + rng.uniform(-0.5, 0.5)
        self.cd = rng.uniform(0.75, 1.05)
        self.limit = 40
        self.title = f"{fmt(self.target)} balls in {self.limit} seconds?"
        self.sub = "every bounce splits a ball – the gap spins"
        self.peak = 1

    def start(self, w):
        w.spawn(CX + self.rng.uniform(-60, 60), CY - 200, self.rng.uniform(-300, 300), 0, 10, 0)

    def gap_ang(self, t):
        return self.ga0 + self.gw * t

    def colliders(self, t):
        return [], [], [(CX, CY, self.R, 14, self.gap_ang(t), self.gap / 2)]

    def rules(self, w, dt_frame):
        n = w.n
        d = np.hypot(w.x[:n] - CX, w.y[:n] - CY)
        inside = d < self.R + 5
        if self.outcome is None:
            for i in np.where((w.hit[:n] > 0) & inside & (w.cool[:n] <= 0))[0]:
                j = w.split(i, self.rng)
                if j >= 0:
                    w.cool[i] = self.cd; w.cool[j] = self.cd
                    self.ev('pop', w.x[i])
        w.hit[:n] = 0
        # Herausgefallene: unter den Bildrand -> weg
        gone = (~inside) & (w.y[:n] > H + 40)
        w.alive[:n][gone] = False
        lost = int(((d > self.R + 5) & (d < self.R + 40)).sum())
        if lost:
            self.ev('plop', lost)
        cnt = int(inside.sum())
        self.peak = max(self.peak, cnt)
        self.hist.append(cnt)
        if self.outcome is None:
            if cnt >= self.target: self.outcome = 'win'
            elif cnt == 0: self.outcome = 'lose'
            elif len(self.hist) >= self.limit * FPS: self.outcome = 'time'
            self.count = cnt

    def draw(self, ctx, t):
        ga = self.gap_ang(t)
        ring_draw(ctx, CX, CY, self.R, ga, self.gap, (0.62, 0.55, 1.0))

    def hud(self, ctx):
        counter(ctx, fmt(self.count), self.count / self.target, danger=self.count < self.peak * 0.5 and self.peak > 20)
        left = max(0, self.limit - len(self.hist) / FPS)
        text(ctx, f"{left:0.1f}s", W / 2, 1810, 54, (0.98, 0.38, 0.38) if left < 10 else (0.68, 0.68, 0.78))

    def end_text(self):
        return {'win': ("YOU MADE IT!", True), 'time': ("TIME'S UP!", False)}.get(self.outcome, ("ALL GONE!", False))

    def drama(self, secs):
        h = np.array(self.hist)
        if self.outcome is None or secs < 18 or secs > 52:
            return -1
        if self.outcome == 'win':
            pk = int(np.argmax(h > self.target * 0.5)) if (h > self.target * 0.5).any() else 0
            dip = h[len(h) // 3:].min() / self.target
            return 1.0 + (0.5 - min(dip, 0.5))
        if self.outcome == 'time':
            return 1.2 + self.peak / self.target if self.peak >= self.target * 0.75 else -1
        return (self.peak / self.target) if self.peak >= self.target * 0.45 else -1


class HexMode(RingMode):
    """5 Sechseck: dreht sich, eine Seite offen, Bälle werden schneller."""
    name = 'hexagon'
    vmin, vmax = 520.0, 1700.0

    def __init__(self, rng):
        super().__init__(rng)
        self.R = 480.0
        self.wr = rng.choice([-1, 1]) * rng.uniform(0.45, 0.8)
        self.open = rng.randrange(6)
        self.hole = rng.uniform(0.22, 0.32)
        self.sub = "the hexagon spins – one side has a hole"
        self.title = f"{fmt(self.target)} balls in {self.limit} seconds?"

    def corners(self, t):
        a0 = self.wr * t
        return [(CX + self.R * math.cos(a0 + k * math.pi / 3), CY + self.R * math.sin(a0 + k * math.pi / 3)) for k in range(6)]

    def colliders(self, t):
        c = self.corners(t)
        segs = []
        for k in range(6):
            if k == self.open:
                continue
            (x1, y1), (x2, y2) = c[k], c[(k + 1) % 6]
            segs.append((x1, y1, x2, y2, 16, CX, CY, self.wr))
        segs += self.open_parts(c)
        return segs, [], []

    def open_parts(self, c):
        (x1, y1), (x2, y2) = c[self.open], c[(self.open + 1) % 6]
        f = (1 - self.hole) / 2
        a = (x1 + (x2 - x1) * f, y1 + (y2 - y1) * f); b = (x2 - (x2 - x1) * f, y2 - (y2 - y1) * f)
        return [(x1, y1, a[0], a[1], 16, CX, CY, self.wr), (b[0], b[1], x2, y2, 16, CX, CY, self.wr)]

    def rules(self, w, dt_frame):
        n = w.n
        # Beschleunigen bei jedem Abprall
        h = w.hit[:n] > 0
        w.vx[:n][h] *= 1.025; w.vy[:n][h] *= 1.025
        super().rules(w, dt_frame)

    def draw(self, ctx, t):
        c = self.corners(t)
        glow_line(ctx, [(c[k], c[(k + 1) % 6]) for k in range(6) if k != self.open] +
                  [((p[0], p[1]), (p[2], p[3])) for p in self.open_parts(c)], (0.99, 0.60, 0.35))


class RingsMode(Mode):
    """2 Ringe ausbrechen: 4 Ringe, jeder mit Lücke."""
    name = 'rings'
    gravity = 0.0
    vmin, vmax = 520.0, 950.0
    maxdur = 50.0

    def __init__(self, rng):
        super().__init__(rng)
        self.radii = [140.0, 245.0, 350.0, 455.0]
        self.gaps = [math.radians(rng.uniform(17, 24)) for _ in self.radii]
        self.ws = [(-1) ** k * rng.uniform(0.5, 1.2) for k in range(4)]
        self.a0 = [rng.uniform(0, 2 * math.pi) for _ in self.radii]
        self.cap = rng.choice([6, 10, 16])
        self.limit = 35
        self.title = f"Can a ball escape in {self.limit}s?"
        self.sub = "4 spinning rings – every bounce splits"
        self.layer = 0
        self.cols = [(0.35, 0.65, 0.98), (0.40, 0.88, 0.62), (0.99, 0.75, 0.30), (0.98, 0.42, 0.42)]

    def start(self, w):
        a = self.rng.uniform(0, 2 * math.pi)
        w.spawn(CX, CY, math.cos(a) * 600, math.sin(a) * 600, 11, 0)

    def colliders(self, t):
        return [], [], [(CX, CY, R, 12, self.a0[k] + self.ws[k] * t, self.gaps[k] / 2) for k, R in enumerate(self.radii)]

    def rules(self, w, dt_frame):
        n = w.n
        if self.outcome is None and n < self.cap:
            for i in np.where((w.hit[:n] > 0) & (w.cool[:n] <= 0))[0]:
                if w.n >= self.cap: break
                j = w.split(i, self.rng)
                if j >= 0:
                    w.cool[i] = 1.2; w.cool[j] = 1.2; self.ev('pop', w.x[i])
        w.hit[:n] = 0
        d = np.hypot(w.x[:n] - CX, w.y[:n] - CY)
        layer = int(max((d > R + 6).sum() for R in [0]) if False else 0)
        best = 0
        for dd in d:
            best = max(best, sum(1 for R in self.radii if dd > R + 8))
        if best > self.layer:
            self.ev('ding', 600 + best * 150)
        self.layer = max(self.layer, best)
        self.hist.append(best)
        if self.outcome is None and best >= 4:
            self.outcome = 'win'
        elif self.outcome is None and len(self.hist) >= self.limit * FPS:
            self.outcome = 'lose'

    def draw(self, ctx, t):
        for k, R in enumerate(self.radii):
            ring_draw(ctx, CX, CY, R, self.a0[k] + self.ws[k] * t, self.gaps[k], self.cols[k], lw=12)

    def hud(self, ctx):
        counter(ctx, f"LAYER {min(self.layer, 4)} / 4", min(self.layer, 4) / 4)
        left = max(0, self.limit - len(self.hist) / FPS)
        text(ctx, f"{left:0.1f}s", W / 2, 1810, 54, (0.98, 0.38, 0.38) if left < 10 else (0.68, 0.68, 0.78))

    def end_text(self):
        return ("ESCAPED!", True) if self.outcome == 'win' else ("TRAPPED!", False)

    def drama(self, secs):
        if self.outcome == 'win' and 15 <= secs <= 48:
            return 1.0 + secs / 40
        if self.outcome == 'lose' and self.layer >= 3:
            return 0.9
        return -1


class PlinkoMode(Mode):
    """3 Plinko: Bälle fallen durch Stifte, Fächer x0/x1/x2/x3."""
    name = 'plinko'
    gravity = 1700.0
    rest = 0.55
    ball_ball = False

    def __init__(self, rng):
        super().__init__(rng)
        self.target = rng.choice([200, 300, 500])
        side = rng.choice([['x0', 'x2'], ['x2', 'x0']])
        edge = rng.choice(['x3', 'x0'])
        self.bins = [edge, side[0], side[1], 'x1', side[1], side[0], edge]
        self.bw = 1000 / len(self.bins)
        self.top, self.bin_y = 420.0, 1380.0
        self.pegs = []
        rows = 12
        for r in range(rows):
            y = self.top + 40 + r * 75
            off = (r % 2) * 45
            for k in range(-6, 7):
                x = CX + k * 90 + off - 45
                if 70 < x < W - 70:
                    self.pegs.append((x, y, 7.0))
        self.queue = rng.choice([4, 6, 8])
        self.spawn_t = 0.0
        self.title = f"Will it reach {fmt(self.target)}?"
        self.sub = "x2 doubles – x0 deletes"
        self.flash = {}

    def start(self, w):
        pass

    def colliders(self, t):
        segs = [(40, 300, 40, 1500, 16, 0, 0, 0), (W - 40, 300, W - 40, 1500, 16, 0, 0, 0)]
        for k in range(1, len(self.bins)):
            x = 40 + k * self.bw
            segs.append((x, self.bin_y - 30, x, self.bin_y + 110, 10, 0, 0, 0))
        return segs, self.pegs, []

    def rules(self, w, dt_frame):
        self.spawn_t += dt_frame
        while self.queue > 0 and self.spawn_t > 0.07 and self.outcome is None:
            self.spawn_t -= 0.07
            self.queue -= 1
            w.spawn(CX + self.rng.uniform(-60, 60), 330, self.rng.uniform(-80, 80), 0, 11, self.rng.randrange(5))
        n = w.n
        landed = np.where(w.alive[:n] & (w.y[:n] > self.bin_y + 30))[0]
        for i in landed:
            b = int(min(len(self.bins) - 1, max(0, (w.x[i] - 40) // self.bw)))
            m = int(self.bins[b][1])
            w.alive[i] = False
            self.queue += m
            self.flash[b] = 8
            self.ev('ding' if m > 1 else ('plop' if m == 0 else 'pop'), 500 + m * 150)
        w.hit[:n] = 0
        cnt = int(w.alive[:n].sum()) + self.queue
        if self.outcome is None:
            self.count = cnt
        self.hist.append(cnt)
        if self.outcome is None:
            if cnt >= self.target: self.outcome = 'win'
            elif cnt == 0: self.outcome = 'lose'

    def draw(self, ctx, t):
        ctx.new_path(); ctx.set_source_rgb(0.80, 0.82, 0.95)
        for (x, y, r) in self.pegs:
            ctx.move_to(x + r, y); ctx.arc(x, y, r, 0, 2 * math.pi)
        ctx.fill()
        glow_line(ctx, [((40, 300), (40, 1500)), ((W - 40, 300), (W - 40, 1500))], (0.62, 0.55, 1.0), lw=10)
        bc = {'x0': (0.95, 0.35, 0.35), 'x1': (0.55, 0.56, 0.68), 'x2': (0.99, 0.75, 0.30), 'x3': (0.40, 0.92, 0.60)}
        for k, b in enumerate(self.bins):
            x = 40 + k * self.bw
            f = self.flash.get(k, 0)
            col = bc[b]
            if f: col = tuple(min(1, c + 0.3) for c in col); self.flash[k] = f - 1
            ctx.new_path(); ctx.set_source_rgb(*col); ctx.rectangle(x + 6, self.bin_y, self.bw - 12, 90); ctx.fill()
            text(ctx, b, x + self.bw / 2, self.bin_y + 60, 40, (0.05, 0.05, 0.08))

    def hud(self, ctx):
        counter(ctx, fmt(self.count), self.count / self.target, y=1620)

    def end_text(self):
        return ("YOU MADE IT!", True) if self.outcome == 'win' else ("ALL GONE!", False)

    def drama(self, secs):
        h = np.array(self.hist)
        if self.outcome is None or secs < 15 or secs > 52:
            return -1
        if self.outcome == 'win':
            return 1.0 + (0.4 - min(0.4, h[len(h) // 4:].min() / self.target))
        return h.max() / self.target if h.max() >= self.target * 0.4 else -1


class VersusMode(Mode):
    """4 Rot gegen Blau: Abprall teilt das eigene Team, Zusammenstöße bekehren."""
    name = 'versus'
    gravity = 0.0
    vmin, vmax = 430.0, 800.0

    def __init__(self, rng):
        super().__init__(rng)
        self.R = 470.0
        self.target = rng.choice([300, 400, 400])
        self.cap = int(self.target * 1.6)
        self.title = "RED vs BLUE"
        self.sub = f"first to {self.target} wins – hits convert"
        self.leader = 0
        self.changes = 0

    def start(self, w):
        w.spawn(CX - 150, CY, self.rng.uniform(300, 500), self.rng.uniform(-400, 400), 11, 0, 0)
        w.spawn(CX + 150, CY, -self.rng.uniform(300, 500), self.rng.uniform(-400, 400), 11, 0, 1)

    def colliders(self, t):
        return [], [], [(CX, CY, self.R, 14, 0.0, 0.0)]

    def rules(self, w, dt_frame):
        n = w.n
        if self.outcome is None and n < self.cap:
            for i in np.where((w.hit[:n] > 0) & (w.cool[:n] <= 0))[0]:
                if w.n >= self.cap: break
                j = w.split(i, self.rng)
                if j >= 0:
                    w.cool[i] = 0.9; w.cool[j] = 0.9; self.ev('pop', w.x[i])
        w.hit[:n] = 0
        n = w.n
        red = int((w.team[:n] == 0).sum()); blue = n - red
        self.red, self.blue = red, blue
        lead = 0 if red > blue else (1 if blue > red else self.leader)
        if lead != self.leader and n > 6:
            self.changes += 1
        self.leader = lead
        self.hist.append(red - blue)
        if self.outcome is None:
            if red >= self.target or blue == 0: self.outcome = 'red'
            elif blue >= self.target or red == 0: self.outcome = 'blue'

    def conversions(self, w, pairs):
        for i, j in pairs:
            si = math.hypot(w.vx[i], w.vy[i]); sj = math.hypot(w.vx[j], w.vy[j])
            if self.rng.random() < 0.35:
                if si > sj: w.team[j] = w.team[i]
                else: w.team[i] = w.team[j]
                self.ev('ding', 700)

    def draw(self, ctx, t):
        ring_draw(ctx, CX, CY, self.R, 0, 0, (0.75, 0.75, 0.85))

    def hud(self, ctx):
        tot = max(1, self.red + self.blue)
        ctx.new_path(); ctx.set_source_rgb(*RED); ctx.rectangle(90, 1600, 900 * self.red / tot, 34); ctx.fill()
        ctx.new_path(); ctx.set_source_rgb(*BLUE); ctx.rectangle(90 + 900 * self.red / tot, 1600, 900 * self.blue / tot, 34); ctx.fill()
        text(ctx, f"RED {self.red}", 280, 1710, 64, RED)
        text(ctx, f"BLUE {self.blue}", 800, 1710, 64, BLUE)

    def end_text(self):
        return ("RED WINS!", 'red') if self.outcome == 'red' else ("BLUE WINS!", 'blue')

    def drama(self, secs):
        if self.outcome is None or secs < 18 or secs > 52:
            return -1
        return 0.5 + 0.25 * min(self.changes, 6)


class CupMode(Mode):
    """6 Becher füllen: Bälle teilen sich am Brett, der Boden hat Löcher."""
    name = 'cup'
    gravity = 1500.0
    rest = 0.6
    maxdur = 50.0

    def __init__(self, rng):
        super().__init__(rng)
        self.cx0, self.cy0 = 220.0, 980.0
        self.bottom = 1460.0
        self.hole = rng.uniform(32, 42)
        self.holes = sorted([rng.uniform(380, 480), rng.uniform(600, 700)])
        self.drops = rng.choice([45, 55, 65])
        self.paddle_w = rng.uniform(1.0, 1.6)
        self.full_line = 1240.0
        self.mult = rng.choice([4, 4, 5])
        self.after = 0.0
        self.title = "Will the cup fill up?"
        self.sub = "the paddle splits balls – the floor leaks"
        self.spawn_t = 0.0
        self.fill = 0.0
        self.best = 0.0

    def start(self, w):
        pass

    def paddle(self, t):
        x = CX + 260 * math.sin(self.paddle_w * t)
        return (x - 120, 700, x + 120, 700)

    def colliders(self, t):
        x1, y1, x2, y2 = self.paddle(t)
        segs = [(x1, y1, x2, y2, 18, 0, 0, 0),
                (60, 900, 260, self.bottom, 16, 0, 0, 0), (1020, 900, 820, self.bottom, 16, 0, 0, 0)]
        xs = [260] + [v for h in self.holes for v in (h - self.hole / 2, h + self.hole / 2)] + [820]
        for k in range(0, len(xs), 2):
            segs.append((xs[k], self.bottom, xs[k + 1], self.bottom, 16, 0, 0, 0))
        return segs, [], []

    def rules(self, w, dt_frame):
        self.spawn_t += dt_frame
        if self.drops > 0 and self.spawn_t > 0.35 and self.outcome is None:
            self.spawn_t = 0; self.drops -= 1
            w.spawn(CX + self.rng.uniform(-250, 250), 420, self.rng.uniform(-60, 60), 0, 13, self.rng.randrange(5))
        n = w.n
        if self.outcome is None:
            for i in np.where((w.hit[:n] > 0) & (w.cool[:n] <= 0) & (w.y[:n] < 760))[0]:
                w.cool[i] = 0.5
                for _ in range(self.mult - 1):
                    j = w.split(i, self.rng, 0.9)
                    if j >= 0: w.cool[j] = 0.5
                self.ev('pop', w.x[i])
        w.hit[:n] = 0
        w.alive[:n][w.y[:n] > H + 40] = False
        leaking = int(((w.y[:n] > self.bottom + 10) & (w.y[:n] < self.bottom + 40)).sum())
        if leaking:
            self.ev('plop', leaking)
        sp = np.hypot(w.vx[:n], w.vy[:n])
        settled = (w.y[:n] > self.full_line - 60) & (w.y[:n] < self.bottom) & (w.x[:n] > 120) & (w.x[:n] < 960) & (sp < 260)
        ys = np.sort(w.y[:n][settled])
        level = ys[min(len(ys) - 1, 8)] - 13 if len(ys) > 20 else self.bottom
        self.fill = max(0.0, min(1.0, (self.bottom - level) / (self.bottom - self.full_line)))
        self.best = max(self.best, self.fill)
        self.hist.append(self.fill)
        if self.outcome is None:
            if self.fill >= 1.0: self.outcome = 'win'
            elif self.drops == 0:
                self.after += dt_frame
                if self.after > 6 or n == 0: self.outcome = 'lose'

    def draw(self, ctx, t):
        x1, y1, x2, y2 = self.paddle(t)
        glow_line(ctx, [((x1, y1), (x2, y2))], (0.99, 0.75, 0.30), lw=18)
        lines = [((60, 900), (260, self.bottom)), ((1020, 900), (820, self.bottom))]
        xs = [260] + [v for h in self.holes for v in (h - self.hole / 2, h + self.hole / 2)] + [820]
        for k in range(0, len(xs), 2):
            lines.append(((xs[k], self.bottom), (xs[k + 1], self.bottom)))
        glow_line(ctx, lines, (0.75, 0.78, 0.95))
        ctx.save(); ctx.set_dash([18, 12]); ctx.set_line_width(5); ctx.set_source_rgb(0.40, 0.95, 0.55)
        ctx.new_path(); ctx.move_to(170, self.full_line); ctx.line_to(910, self.full_line); ctx.stroke(); ctx.restore()
        text(ctx, "FULL", 975, self.full_line + 14, 34, (0.40, 0.95, 0.55))

    def hud(self, ctx):
        counter(ctx, f"{int(self.fill * 100)} %", self.fill, y=1660)

    def end_text(self):
        return ("FULL!", True) if self.outcome == 'win' else (f"ONLY {int(self.best * 100)} %", False)

    def drama(self, secs):
        if self.outcome == 'win' and 18 <= secs <= 50:
            return 1.2
        if self.outcome != 'win' and self.best >= 0.8 and secs <= 52:
            return self.best
        return -1


MODES = {'ring': RingMode, 'rings': RingsMode, 'plinko': PlinkoMode, 'versus': VersusMode, 'hexagon': HexMode, 'cup': CupMode}


# ------------------------------------------------------------------ Zeichnen
def text(ctx, s, x, y, size, col, bold=True, maxw=1000):
    ctx.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    e = ctx.text_extents(s)
    if e.width > maxw:
        ctx.set_font_size(size * maxw / e.width); e = ctx.text_extents(s)
    ctx.move_to(x - e.width / 2 - e.x_bearing, y); ctx.set_source_rgb(*col); ctx.show_text(s)


def ring_draw(ctx, cx, cy, R, ga, gap, col, lw=16):
    for w_, al in ((lw * 3.2, 0.07), (lw * 2.0, 0.14), (lw, 1.0)):
        ctx.new_path(); ctx.set_line_width(w_); ctx.set_source_rgba(*col, al)
        if gap > 0:
            ctx.arc(cx, cy, R, ga + gap / 2, ga - gap / 2 + 2 * math.pi)
        else:
            ctx.arc(cx, cy, R, 0, 2 * math.pi)
        ctx.stroke()
    if gap > 0:
        for sgn in (-1, 1):
            a = ga + sgn * gap / 2
            ctx.new_path(); ctx.set_source_rgb(1.0, 0.35, 0.35)
            ctx.arc(cx + math.cos(a) * R, cy + math.sin(a) * R, lw * 0.9, 0, 2 * math.pi); ctx.fill()


def glow_line(ctx, lines, col, lw=16):
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for w_, al in ((lw * 3.2, 0.07), (lw * 2.0, 0.14), (lw, 1.0)):
        ctx.new_path(); ctx.set_line_width(w_); ctx.set_source_rgba(*col, al)
        for (a, b) in lines:
            ctx.move_to(*a); ctx.line_to(*b)
        ctx.stroke()


def counter(ctx, s, prog, danger=False, y=1640):
    text(ctx, s, W / 2, y, 100, (1, 1, 1))
    ctx.new_path(); ctx.set_source_rgb(0.18, 0.18, 0.26); ctx.rectangle(140, y + 40, 800, 26); ctx.fill()
    col = (0.40, 0.92, 0.55) if prog >= 1 else ((0.95, 0.35, 0.35) if danger else (0.99, 0.75, 0.30))
    ctx.new_path(); ctx.set_source_rgb(*col); ctx.rectangle(140, y + 40, 800 * min(1, prog), 26); ctx.fill()


def draw_balls(ctx, w, mode):
    n = w.n
    trails = n <= 450
    for c in range(5):
        if isinstance(mode, VersusMode):
            if c > 1: break
            idx = np.where(w.alive[:n] & (w.team[:n] == c))[0]
            col = RED if c == 0 else BLUE
        else:
            idx = np.where(w.alive[:n] & (w.col[:n] == c))[0]
            col = mode.pal[c % len(mode.pal)]
        if len(idx) == 0:
            continue
        if trails:
            for k in range(1, TRAIL):
                ctx.new_path(); ctx.set_source_rgba(*col, 0.22 * (TRAIL - k) / TRAIL)
                for i in idx:
                    r = w.rad[i] * (1 - 0.1 * k)
                    ctx.move_to(w.tx[i, k] + r, w.ty[i, k]); ctx.arc(w.tx[i, k], w.ty[i, k], r, 0, 2 * math.pi)
                ctx.fill()
        if n <= 300:
            ctx.new_path(); ctx.set_source_rgba(*col, 0.18)
            for i in idx:
                ctx.move_to(w.x[i] + w.rad[i] * 1.7, w.y[i]); ctx.arc(w.x[i], w.y[i], w.rad[i] * 1.7, 0, 2 * math.pi)
            ctx.fill()
        ctx.new_path(); ctx.set_source_rgb(*col)
        for i in idx:
            ctx.move_to(w.x[i] + w.rad[i], w.y[i]); ctx.arc(w.x[i], w.y[i], w.rad[i], 0, 2 * math.pi)
        ctx.fill()


# ------------------------------------------------------------------ Ton
SR = 44100


def tone(freq, dur, decay, vol=0.5, harm=0.25):
    t = np.arange(int(SR * dur)) / SR
    return (np.sin(2 * np.pi * freq * t) + harm * np.sin(4 * np.pi * freq * t)) * np.exp(-t * decay) * vol


def mix(audio, s, t0):
    i0 = int(t0 * SR)
    if i0 >= len(audio): return
    e = min(len(audio), i0 + len(s))
    audio[i0:e] += s[:e - i0]


# ------------------------------------------------------------------ Ablauf
def run(mode_name, seed, out=None, dry=False):
    rng = random.Random(seed * 1000 + sum(map(ord, mode_name)))
    mode = MODES[mode_name](rng)
    w = World()
    mode.start(w)
    dt = 1.0 / (FPS * SUB)
    frame = 0
    end_frame = None
    audio = np.zeros(int((mode.maxdur + 5) * SR)) if not dry else None
    ff = surf = ctx = None
    if not dry:
        ff = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                               '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', out + '.v.mp4'], stdin=subprocess.PIPE)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H); ctx = cairo.Context(surf)
    while True:
        t = frame / FPS
        mode.events = []
        allpairs = []
        for s in range(SUB):
            segs, pegs, rings = mode.colliders(t + s * dt)
            sa, ns = seg_arr(segs); pa, npg = seg_arr([(p[0], p[1], p[2]) for p in pegs]); ra, nr = ring_arr(rings)
            nconv = substep(w.x, w.y, w.vx, w.vy, w.rad, w.alive, w.hit, w.n, dt, mode.gravity, mode.rest,
                            sa, ns, pa[:, :3].copy(), npg, ra, nr, mode.ball_ball, w.team, w.conv)
            if nconv:
                allpairs.extend([tuple(p) for p in w.conv[:nconv]])
            w.cool[:w.n] -= dt
        mode.speed_clamp(w)
        if allpairs and hasattr(mode, 'conversions'):
            mode.conversions(w, allpairs)
        mode.rules(w, 1.0 / FPS)
        w.compact()
        w.tx[:w.n, 1:] = w.tx[:w.n, :-1]; w.ty[:w.n, 1:] = w.ty[:w.n, :-1]
        w.tx[:w.n, 0] = w.x[:w.n]; w.ty[:w.n, 0] = w.y[:w.n]
        if mode.outcome is None and t >= mode.maxdur:
            mode.outcome = 'timeout'
        if mode.outcome is not None and end_frame is None:
            end_frame = frame
            if not dry:
                _, good = mode.end_text()
                notes = [523, 659, 784, 1047] if good is not False else [523, 440, 349, 262]
                for k, f in enumerate(notes):
                    mix(audio, tone(f, 0.35, 6, 0.6), t + k * 0.12)
        if not dry:
            # Töne
            pops = [e for e in mode.events if e[0] == 'pop'][:5]
            for k, (_, xv) in enumerate(pops):
                cnt = getattr(mode, 'count', w.n)
                f = 420 + 380 * min(1.0, math.log(max(cnt, 1) + 1) / 6.5) + 120 * ((xv - CX) / 540)
                mix(audio, tone(f, 0.07, 55, 0.45 / (1 + 0.3 * k)), t + k * 0.006)
            for (_, v) in [e for e in mode.events if e[0] == 'plop'][:1]:
                mix(audio, tone(150, 0.12, 30, min(0.9, 0.3 + 0.08 * v), 0.4), t)
            for (_, f) in [e for e in mode.events if e[0] == 'ding'][:3]:
                mix(audio, tone(f, 0.25, 12, 0.35, 0.5), t)
            # Bild
            ctx.set_source_rgb(0.035, 0.035, 0.065); ctx.paint()
            text(ctx, mode.title, W / 2, 250, 74 if len(mode.title) < 26 else 64, (1, 1, 1))
            text(ctx, mode.sub, W / 2, 320, 38, (0.68, 0.68, 0.78), bold=False)
            mode.draw(ctx, t)
            draw_balls(ctx, w, mode)
            mode.hud(ctx)
            if end_frame is not None and mode.outcome != 'timeout':
                k = min(1.0, (frame - end_frame) / 8)
                msg, good = mode.end_text()
                col = RED if good == 'red' else BLUE if good == 'blue' else ((0.40, 0.95, 0.55) if good else (0.98, 0.38, 0.38))
                ctx.save(); ctx.translate(W / 2, 470); ctx.scale(0.5 + 0.5 * k, 0.5 + 0.5 * k)
                text(ctx, msg, 0, 0, 110, col); ctx.restore()
            ff.stdin.write(surf.get_data())
        frame += 1
        if end_frame is not None and frame - end_frame > int(2.8 * FPS):
            break
    secs = round(frame / FPS, 1)
    score = mode.drama(secs) if mode.outcome != 'timeout' else -1
    extra = {k: round(float(getattr(mode, k)), 2) for k in ('peak', 'best', 'changes', 'layer') if hasattr(mode, k)}
    info = {**extra, 'mode': mode_name, 'seed': seed, 'title': mode.title, 'outcome': mode.outcome, 'seconds': secs, 'drama': round(float(score), 3)}
    if not dry:
        ff.stdin.close(); ff.wait()
        a = audio[:int(frame / FPS * SR)]
        pk = np.max(np.abs(a)) or 1
        a = np.tanh(a / pk * 1.6) * 0.8
        with wave.open(out + '.a.wav', 'wb') as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
            wf.writeframes((a * 32767).astype(np.int16).tobytes())
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', out + '.v.mp4', '-i', out + '.a.wav', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', out], check=True)
        import os
        os.remove(out + '.v.mp4'); os.remove(out + '.a.wav')
    return info


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='ring', choices=list(MODES))
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--out', default='video.mp4')
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    print(json.dumps(run(a.mode, a.seed, a.out, a.dry)))
