"""Physik-Kern (numba): Bälle gegen Bälle, Stifte, Linien (auch drehend) und Ringe mit Lücken."""
import math
import numpy as np
from numba import njit


@njit(cache=True)
def substep(x, y, vx, vy, rad, alive, hit, n, dt, g, rest,
            segs, nseg, pegs, npeg, rings, nring, ball_ball, team, conv):
    """Ein Teilschritt. hit[i] zählt kräftige Abpraller (für Teilungs-Regeln).
    conv: Paare (i, j) bei Stößen verschiedener Teams werden in conv eingetragen (für Rot-gegen-Blau)."""
    nconv = 0
    for i in range(n):
        if not alive[i]:
            continue
        vy[i] += g * dt
        x[i] += vx[i] * dt
        y[i] += vy[i] * dt

    for i in range(n):
        if not alive[i]:
            continue
        r = rad[i]
        # --- Linien (dicke Segmente, evtl. drehend um Pivot) ---
        for s in range(nseg):
            x1 = segs[s, 0]; y1 = segs[s, 1]; x2 = segs[s, 2]; y2 = segs[s, 3]
            th = segs[s, 4]; px = segs[s, 5]; py = segs[s, 6]; w = segs[s, 7]
            dx = x2 - x1; dy = y2 - y1
            L2 = dx * dx + dy * dy
            t = ((x[i] - x1) * dx + (y[i] - y1) * dy) / L2 if L2 > 0 else 0.0
            if t < 0.0: t = 0.0
            if t > 1.0: t = 1.0
            cx = x1 + t * dx; cy = y1 + t * dy
            qx = x[i] - cx; qy = y[i] - cy
            d = math.sqrt(qx * qx + qy * qy)
            lim = r + th * 0.5
            if d < lim and d > 1e-6:
                nx = qx / d; ny = qy / d
                x[i] += nx * (lim - d); y[i] += ny * (lim - d)
                svx = -w * (cy - py); svy = w * (cx - px)
                rvx = vx[i] - svx; rvy = vy[i] - svy
                vn = rvx * nx + rvy * ny
                if vn < 0:
                    vx[i] -= (1.0 + rest) * vn * nx; vy[i] -= (1.0 + rest) * vn * ny
                    if -vn > 120.0:
                        hit[i] += 1
        # --- Stifte (feste Kreise) ---
        for p in range(npeg):
            qx = x[i] - pegs[p, 0]; qy = y[i] - pegs[p, 1]
            d = math.sqrt(qx * qx + qy * qy)
            lim = r + pegs[p, 2]
            if d < lim and d > 1e-6:
                nx = qx / d; ny = qy / d
                x[i] += nx * (lim - d); y[i] += ny * (lim - d)
                vn = vx[i] * nx + vy[i] * ny
                if vn < 0:
                    vx[i] -= (1.0 + rest * 0.7) * vn * nx; vy[i] -= (1.0 + rest * 0.7) * vn * ny
        # --- Ringe mit Lücke (beidseitig) ---
        for k in range(nring):
            cx = rings[k, 0]; cy = rings[k, 1]; R = rings[k, 2]; th = rings[k, 3]
            ga = rings[k, 4]; gh = rings[k, 5]
            qx = x[i] - cx; qy = y[i] - cy
            d = math.sqrt(qx * qx + qy * qy)
            if d < 1e-6:
                continue
            lim = r + th * 0.5
            if abs(d - R) < lim:
                a = math.atan2(qy, qx)
                da = (a - ga + math.pi) % (2.0 * math.pi) - math.pi
                if abs(da) < gh:
                    continue  # in der Lücke: durchlassen
                nx = qx / d; ny = qy / d
                if d < R:  # innen -> nach innen drücken
                    x[i] = cx + nx * (R - lim); y[i] = cy + ny * (R - lim)
                    vn = vx[i] * nx + vy[i] * ny
                    if vn > 0:
                        vx[i] -= (1.0 + rest) * vn * nx; vy[i] -= (1.0 + rest) * vn * ny
                        if vn > 120.0:
                            hit[i] += 1
                else:      # außen -> nach außen drücken
                    x[i] = cx + nx * (R + lim); y[i] = cy + ny * (R + lim)
                    vn = vx[i] * nx + vy[i] * ny
                    if vn < 0:
                        vx[i] -= (1.0 + rest) * vn * nx; vy[i] -= (1.0 + rest) * vn * ny
                        if -vn > 120.0:
                            hit[i] += 1

    if ball_ball == 0:
        return 0
    # --- Ball gegen Ball (Raster) ---
    cell = 0.0
    for i in range(n):
        if alive[i] and 2.0 * rad[i] > cell:
            cell = 2.0 * rad[i]
    if cell <= 0:
        return 0
    minx = 1e9; miny = 1e9; maxx = -1e9; maxy = -1e9
    for i in range(n):
        if alive[i]:
            if x[i] < minx: minx = x[i]
            if y[i] < miny: miny = y[i]
            if x[i] > maxx: maxx = x[i]
            if y[i] > maxy: maxy = y[i]
    gw = int((maxx - minx) / cell) + 1
    gh2 = int((maxy - miny) / cell) + 1
    if gw * gh2 > 400000:
        return 0
    head = -np.ones(gw * gh2, np.int64)
    nxt = -np.ones(n, np.int64)
    for i in range(n):
        if not alive[i]:
            continue
        k = int((y[i] - miny) / cell) * gw + int((x[i] - minx) / cell)
        nxt[i] = head[k]; head[k] = i
    for i in range(n):
        if not alive[i]:
            continue
        gx = int((x[i] - minx) / cell); gy = int((y[i] - miny) / cell)
        for oy in range(-1, 2):
            for ox in range(-1, 2):
                hx = gx + ox; hy = gy + oy
                if hx < 0 or hy < 0 or hx >= gw or hy >= gh2:
                    continue
                j = head[hy * gw + hx]
                while j != -1:
                    if j > i:
                        dx = x[j] - x[i]; dy = y[j] - y[i]
                        md = rad[i] + rad[j]
                        d2 = dx * dx + dy * dy
                        if d2 < md * md and d2 > 1e-9 and ball_ball == 2:
                            # nur Berührung erkennen, kein Abprallen (Bälle fliegen durcheinander durch)
                            d = math.sqrt(d2)
                            rv = ((vx[j] - vx[i]) * dx + (vy[j] - vy[i]) * dy) / d
                            if team[i] != team[j] and nconv < conv.shape[0] and rv < 0:
                                conv[nconv, 0] = i; conv[nconv, 1] = j; nconv += 1
                        elif d2 < md * md and d2 > 1e-9:
                            d = math.sqrt(d2)
                            nx = dx / d; ny = dy / d
                            ov = (md - d) * 0.5
                            x[i] -= nx * ov; y[i] -= ny * ov
                            x[j] += nx * ov; y[j] += ny * ov
                            rv = (vx[j] - vx[i]) * nx + (vy[j] - vy[i]) * ny
                            if rv < 0:
                                imp = -(1.0 + rest) * 0.5 * rv
                                vx[i] -= imp * nx; vy[i] -= imp * ny
                                vx[j] += imp * nx; vy[j] += imp * ny
                                if team[i] != team[j] and nconv < conv.shape[0] and -rv > 150.0:
                                    conv[nconv, 0] = i; conv[nconv, 1] = j; nconv += 1
                    j = nxt[j]
    return nconv
