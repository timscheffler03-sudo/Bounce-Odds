import cairo, math

S = 800
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, S, S)
c = cairo.Context(surf)
c.set_source_rgb(0.04, 0.04, 0.08); c.paint()

PAL = [(0.98, 0.42, 0.42), (0.99, 0.75, 0.30), (0.40, 0.88, 0.62), (0.35, 0.65, 0.98), (0.80, 0.55, 0.98)]
cx, cy, R = 370, 370, 215
gap_a, gap = math.radians(40), math.radians(42)

# Leuchtender Ring mit Lücke (Glow durch mehrere breite, transparente Striche)
for lw, al in ((70, 0.06), (46, 0.10), (30, 0.18), (20, 1.0)):
    c.new_path(); c.set_line_width(lw); c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_source_rgba(0.62, 0.55, 1.0, al)
    c.arc(cx, cy, R, gap_a + gap / 2, gap_a - gap / 2 + 2 * math.pi); c.stroke()


def ball(x, y, r, col, trail=None):
    if trail:
        tx, ty = trail
        for k in range(10, 0, -1):
            f = k / 10
            c.new_path(); c.set_source_rgba(*col, 0.10 * (1 - f) + 0.02)
            c.arc(x - tx * f, y - ty * f, r * (1 - 0.5 * f), 0, 2 * math.pi); c.fill()
    for rr, al in ((r * 1.9, 0.12), (r * 1.4, 0.22)):
        c.new_path(); c.set_source_rgba(*col, al); c.arc(x, y, rr, 0, 2 * math.pi); c.fill()
    c.new_path(); c.set_source_rgb(*col); c.arc(x, y, r, 0, 2 * math.pi); c.fill()
    c.new_path(); c.set_source_rgba(1, 1, 1, 0.55); c.arc(x - r * 0.35, y - r * 0.35, r * 0.28, 0, 2 * math.pi); c.fill()


# Bälle im Ring
ball(310, 290, 44, PAL[0], (-150, -110))
ball(430, 430, 38, PAL[3], (170, -60))
ball(280, 460, 32, PAL[1], (-90, 140))
ball(430, 280, 24, PAL[4], (60, 120))
# Bälle, die durch die Lücke entkommen
ex = cx + math.cos(gap_a) * R; ey = cy + math.sin(gap_a) * R
ball(ex + 45, ey + 35, 24, PAL[2], (-110, -80))
ball(ex + 105, ey + 85, 18, PAL[1], (-80, -60))
ball(ex + 155, ey + 130, 13, PAL[0], (-60, -50))

surf.write_to_png('bounce-odds-profilbild.png')
print('ok')
