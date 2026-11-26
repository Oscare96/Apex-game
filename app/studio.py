"""Faceless broadcast graphics, local speech synthesis and a live HLS encoder."""

import math
import subprocess
import tempfile
import time
from contextlib import contextmanager
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FPS, RATE = 30, 48000
SIZE = (1280, 720)
SAMPLES = RATE // FPS
INK, PAPER, LIME, MUTED = "#0c1020", "#f2f3ed", "#d3fc62", "#a4afca"
STATIONS = ("Red", "Green", "Yellow", "Blue")
COLORS = ("#fc8989", "#70dbba", "#ffd36a", "#ada4ff")


@lru_cache
def font(size, bold=False):
    return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)


@lru_cache(maxsize=128)
def say(text):
    # Keep spoken text out of the filter expression, including quotes and punctuation.
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "line.txt").write_text(text)
        cmd = [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "flite=textfile=line.txt:voice=slt",
            "-ar",
            str(RATE),
            "-ac",
            "1",
            "-f",
            "s16le",
            "pipe:1",
        ]
        result = subprocess.run(cmd, cwd=tmp, capture_output=True, check=True, timeout=20)
    pcm = np.frombuffer(result.stdout, dtype="<i2")
    if not pcm.size or not np.any(pcm):
        raise RuntimeError("Speech engine produced no audible samples")
    return pcm


def canvas(title, caption):
    picture = Image.new("RGB", SIZE, INK)
    draw = ImageDraw.Draw(picture)

    def label(x, y, value, size, color=PAPER, bold=False):
        draw.text((x, y), value, fill=color, font=font(size, bold), stroke_width=0)

    label(50, 28, "APEX", 44, LIME, True)
    label(204, 42, "AI GAMING CHARACTER", 22)
    label(888, 38, title, 24, MUTED, True)
    draw.line((50, 100, 1230, 100), fill="#34394f", width=2)
    draw.rounded_rectangle((50, 580, 1230, 684), radius=16, fill="#20273b")
    label(78, 595, "APEX  /  SYNTHETIC VOICE", 16, LIME, True)
    label(78, 629, caption, 27)
    return picture


def frame(env, state, turn, points, caption):
    world = env.unwrapped
    row, col, passenger, dest = map(int, world.decode(state))
    picture = canvas("NIGHT SHIFT   /   TAXI", caption)
    draw = ImageDraw.Draw(picture)

    def label(x, y, value, size, color=PAPER, bold=False):
        draw.text((x, y), value, fill=color, font=font(size, bold))

    # All walls, stops and player positions come from the active environment.
    x0, y0, cell = 66, 130, 84
    for r in range(5):
        for c in range(5):
            x, y = x0 + c * cell, y0 + r * cell
            draw.rounded_rectangle(
                (x + 3, y + 3, x + cell - 3, y + cell - 3), radius=10, fill="#222a40"
            )
            if c < 4 and world.desc[r + 1, 2 * c + 2] == b"|":
                draw.line((x + cell, y + 2, x + cell, y + cell - 2), fill=PAPER, width=6)
    for index, (r, c) in enumerate(world.locs):
        x, y = x0 + c * cell, y0 + r * cell
        draw.ellipse((x + 7, y + 7, x + 30, y + 30), fill=COLORS[index])
        label(x + 11, y + 8, STATIONS[index][0], 13, INK, True)
    x, y = x0 + col * cell + 17, y0 + row * cell + 32
    draw.rounded_rectangle((x, y, x + 49, y + 24), radius=7, fill=LIME)
    draw.rectangle((x + 12, y - 6, x + 36, y + 2), fill=LIME)
    for xx in (x + 7, x + 32):
        draw.ellipse((xx, y + 18, xx + 10, y + 28), fill=INK, outline=PAPER, width=2)
    label(550, 137, "DISPATCH", 21, MUTED, True)
    label(
        546,
        180,
        "Passenger delivered"
        if turn and turn.terminated
        else "Fare on board"
        if passenger == 4
        else "On pickup duty",
        47,
        PAPER,
        True,
    )
    target = dest if passenger == 4 or (turn and turn.terminated) else passenger
    label(
        552,
        282,
        "DESTINATION" if passenger == 4 or (turn and turn.terminated) else "PICKUP",
        19,
        MUTED,
    )
    label(550, 320, STATIONS[target] + " station", 35, COLORS[target], True)
    from .game import ACTIONS

    label(550, 442, "LAST ACTION", 17, MUTED)
    label(550, 473, ACTIONS[turn.action].upper() if turn else "DISPATCHED", 25)
    label(895, 442, "FARE SCORE", 17, MUTED)
    label(895, 473, str(points), 25)
    return picture


@contextmanager
def broadcast(path, realtime, feed=None):
    """Publish playable two-second segments during the episode."""
    opts = {
        "hls_time": "2",
        "hls_playlist_type": "event",
        "hls_list_size": "0",
        "hls_flags": "independent_segments+temp_file",
        "hls_segment_filename": str(path / "part-%05d.ts"),
    }
    with av.open(str(path / "live.m3u8"), "w", format="hls", options=opts) as container:
        video = container.add_stream("libx264", rate=FPS)
        video.width, video.height = SIZE
        video.pix_fmt = "yuv420p"
        video.codec_context.thread_count = 2
        video.options = {
            "preset": "veryfast",
            "tune": "zerolatency",
            "crf": "21",
            "x264-params": "keyint=60:min-keyint=60:scenecut=0",
        }
        sound = container.add_stream("aac", rate=RATE)
        sound.layout = "mono"
        sound.bit_rate = 96000
        count = 0
        start = time.monotonic()

        def scene(image, speech, minimum=0.65):
            nonlocal count
            duration = max(math.ceil(minimum * FPS), math.ceil(len(speech) / SAMPLES))
            samples = np.zeros(duration * SAMPLES, dtype=np.int16)
            samples[: len(speech)] = speech
            template = av.VideoFrame.from_image(image).reformat(format="yuv420p")
            for offset in range(duration):
                template.pts = count
                template.time_base = Fraction(1, FPS)
                container.mux(video.encode(template))
                wave = av.AudioFrame.from_ndarray(
                    samples[offset * SAMPLES : (offset + 1) * SAMPLES][None, :],
                    format="s16",
                    layout="mono",
                )
                wave.sample_rate = RATE
                wave.pts = count * SAMPLES
                wave.time_base = Fraction(1, RATE)
                container.mux(sound.encode(wave))
                if feed is not None:
                    feed.write(template, wave)
                count += 1
                if realtime:
                    time.sleep(max(0, start + count / FPS - time.monotonic()))
            return duration / FPS

        yield scene
        container.mux(video.encode())
        container.mux(sound.encode())
        if realtime and feed is not None:
            feed.start_break()


def portrait(image, caption):
    # Preserve original positions and walls. Reflow the same scene for a phone.
    canvas = Image.new("RGB", (720, 1280), INK)
    canvas.paste(image.crop((42, 15, 528, 91)).resize((657, 103)), (28, 20))
    canvas.paste(image.crop((54, 118, 500, 564)).resize((640, 640)), (40, 148))
    canvas.paste(image.crop((540, 136, 1210, 388)).resize((670, 252)), (32, 805))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((24, 1075, 696, 1254), radius=18, fill="#20273b")
    draw.text((46, 1092), "APEX  /  SYNTHETIC VOICE", font=font(21, True), fill=LIME)
    lines = [""]
    for word in caption.split():
        line = (lines[-1] + " " + word).strip()
        if draw.textlength(line, font=font(31)) > 620:
            lines.append(word)
        else:
            lines[-1] = line
    draw.multiline_text((46, 1132), "\n".join(lines), font=font(31), fill=PAPER, spacing=5)
    return canvas


def export_media(path, highlight_start, scenes, elapsed):
    ff = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(
        ff
        + [
            "-i",
            str(path / "live.m3u8"),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(path / "episode.mp4"),
        ],
        check=True,
        timeout=120,
    )
    selected = [s for s in scenes if s[0] + 0.001 >= highlight_start]
    inputs = []
    for _, duration, png in selected:
        inputs.extend([f"file '{png.name}'", f"duration {duration:.6f}"])
    inputs.append(f"file '{selected[-1][2].name}'")
    manifest = selected[0][2].parent / "frames.txt"
    manifest.write_text("\n".join(inputs) + "\n")
    subprocess.run(
        ff
        + [
            "-f",
            "concat",
            "-safe",
            "1",
            "-i",
            str(manifest),
            "-ss",
            f"{selected[0][0]:.6f}",
            "-i",
            str(path / "episode.mp4"),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{elapsed - selected[0][0]:.6f}",
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(path / "highlight.mp4"),
        ],
        check=True,
        timeout=120,
    )
