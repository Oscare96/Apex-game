"""Original four-in-a-row game with legal gravity moves and two independent players."""

from random import Random

from PIL import ImageDraw

from .personality import DISCLOSURE
from .studio import COLORS, INK, LIME, MUTED, PAPER, canvas, font

GAME = "FourInARow-v1"
POLICY = "alpha-beta-4ply-v1"
ORDER = (3, 2, 4, 1, 5, 0, 6)
WINDOWS = tuple(
    sum(1 << ((c + i * dc) * 7 + r + i * dr) for i in range(4))
    for c in range(7)
    for r in range(6)
    for dc, dr in ((0, 1), (1, 0), (1, 1), (1, -1))
    if 0 <= c + 3 * dc < 7 and 0 <= r + 3 * dr < 6
)
COLUMN_MASK = (1 << 6) - 1


def won(bits):
    for stride in (1, 7, 6, 8):
        pairs = bits & (bits >> stride)
        if pairs & (pairs >> (2 * stride)):
            return True
    return False


def options(occupied):
    for col in ORDER:
        row = ((occupied >> (7 * col)) & COLUMN_MASK).bit_count()
        if row < 6:
            yield col, 1 << (7 * col + row)


def value(mine, other):
    weights = (0, 1, 6, 32, 200)
    total = 0
    for window in WINDOWS:
        a = (mine & window).bit_count()
        b = (other & window).bit_count()
        if not b:
            total += weights[a]
        elif not a:
            total -= weights[b]
    return total


def search(mine, other, depth, alpha, beta):
    if won(other):
        return -10000 - depth, None
    if not depth:
        return value(mine, other), None
    best = -20000
    choice = None
    for col, bit in options(mine | other):
        score = -search(other, mine | bit, depth - 1, -beta, -alpha)[0]
        if score > best:
            best, choice = score, col
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return (best, choice) if choice is not None else (0, None)


def rival(mine, other, rng):
    legal = list(options(mine | other))
    for side in (mine, other):
        for col, bit in legal:
            if won(side | bit):
                return col
    return rng.choice(legal)[0]


def drop(apex, cpu, actor, col):
    legal = dict(options(apex | cpu))
    if type(col) is not int or col not in legal:
        raise ValueError("Illegal column")
    bit = legal[col]
    if actor == 1:
        apex |= bit
    else:
        cpu |= bit
    result = "playing"
    if won(apex) or won(cpu):
        result = "apex" if actor == 1 else "cpu"
    elif (apex | cpu).bit_count() == 42:
        result = "draw"
    return {
        "player": actor,
        "column": col,
        "row": (bit.bit_length() - 1) % 7,
        "apex_bits": apex,
        "cpu_bits": cpu,
        "result": result,
    }


def moves(seed):
    apex = cpu = 0
    rng = Random(seed)
    actor = 1 + seed % 2
    while True:
        col = search(apex, cpu, 4, -20000, 20000)[1] if actor == 1 else rival(cpu, apex, rng)
        row = drop(apex, cpu, actor, col)
        yield row
        if row["result"] != "playing":
            return
        actor = 3 - actor
        apex, cpu = row["apex_bits"], row["cpu_bits"]


def replay(seed, trace):
    if not 1 <= len(trace) <= 42:
        raise ValueError("Invalid four-in-a-row replay length")
    apex = cpu = 0
    actor = 1 + seed % 2
    for index, step in enumerate(trace):
        row = drop(apex, cpu, actor, step["column"])
        if row != step or (row["result"] != "playing") != (index == len(trace) - 1):
            raise ValueError(f"Board replay mismatch at move {index + 1}")
        apex, cpu = row["apex_bits"], row["cpu_bits"]
        actor = 3 - actor
    score = {"apex": 1, "cpu": -1, "draw": 0}[trace[-1]["result"]]
    return int(score == 1), score


def board_image(row, caption):
    image = canvas("FOUR IN A ROW", caption)
    draw = ImageDraw.Draw(image)
    left, top, cell = 60, 164, 62
    a, b = (row["apex_bits"], row["cpu_bits"]) if row else (0, 0)
    draw.rounded_rectangle((left, top, left + 7 * cell, top + 6 * cell), radius=14, fill="#29334f")
    for c in range(7):
        for r in range(6):
            bit = 1 << (c * 7 + r)
            x, y = left + c * cell + 7, top + (5 - r) * cell + 7
            color = LIME if a & bit else COLORS[3] if b & bit else INK
            last = row and row["column"] == c and row["row"] == r
            draw.ellipse(
                (x, y, x + 48, y + 48), fill=color, outline=PAPER if last else None, width=3
            )
    result = row["result"] if row else "playing"
    heading = {
        "playing": "Find a line of four",
        "apex": "APEX wins",
        "cpu": "Rival wins",
        "draw": "Board drawn",
    }[result]
    draw.text((550, 142), "TABLE GAME", font=font(21, True), fill=MUTED)
    draw.text((546, 185), heading, font=font(46, True), fill=PAPER)
    draw.text((550, 278), "APEX   ●", font=font(30, True), fill=LIME)
    draw.text((775, 278), "RIVAL   ●", font=font(30, True), fill=COLORS[3])
    draw.text((550, 440), "LAST MOVE", font=font(17), fill=MUTED)
    last = (
        ("APEX" if row["player"] == 1 else "Rival") + f"  /  column {row['column'] + 1}"
        if row
        else "Opening board"
    )
    draw.text((550, 478), last, font=font(26), fill=PAPER)
    return image


def scenes(seed):
    line = DISCLOSURE + " Four in a Row. I call the green pieces."
    yield board_image(None, line), line, line, None, False
    for step in moves(seed):
        result = step["result"]
        line = {
            "apex": "Four in a row. I finally got my ducks organized.",
            "cpu": "Four for my rival. I have officially been outnumbered.",
            "draw": "A full board and no winner. That is an awkward group photo.",
        }.get(result)
        if not line and (step["cpu_bits"] | step["apex_bits"]).bit_count() == 5:
            line = "Seven columns. Somehow I still want a corner office."
        who = "APEX" if step["player"] == 1 else "The rival"
        caption = line or f"{who} played column {step['column'] + 1}."
        yield board_image(step, caption), caption, line, step, False
