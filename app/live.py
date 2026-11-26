"""Send only an explicitly selected APEX feed to a fixed RTMPS provider endpoint."""

import json
import re
import threading
import time
from fractions import Fraction

import av
import numpy as np
from PIL import Image, ImageDraw

from .studio import FPS, INK, LIME, PAPER, RATE, SAMPLES, SIZE, font

HOSTS = {
    "twitch": "rtmps://ingest.global-contribute.live-video.net:443/app/",
    "twitch-test": "rtmps://ingest.global-contribute.live-video.net:443/app/",
    "youtube": "rtmps://a.rtmps.youtube.com:443/live2/",
}


def destination(platform, config):
    key = json.loads(config.read_text())[platform.split("-")[0] + "_stream_key"]
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", key):
        raise ValueError("Invalid stream key format")
    return HOSTS[platform] + key + ("?bandwidthtest=true" if platform == "twitch-test" else "")


class LiveFeed:
    """An encoder stays connected across fares. Its packet clock is independent of local files."""

    def __init__(self, target):
        self.target = target
        self.output = None
        self.frames = 0
        self.failed = False
        self._idle_stop = threading.Event()
        self._idle_thread = None

    def start(self):
        self.output = av.open(
            self.target,
            "w",
            format="flv",
            options={
                "rw_timeout": "8000000",
                "tls_verify": "1",
                "ca_file": "/etc/ssl/certs/ca-certificates.crt",
                "flvflags": "no_duration_filesize",
            },
        )
        self.video = self.output.add_stream("libx264", rate=FPS)
        self.video.width, self.video.height = SIZE
        self.video.pix_fmt = "yuv420p"
        self.video.bit_rate = 2500000
        self.video.codec_context.thread_count = 2
        self.video.options = {
            "preset": "veryfast",
            "tune": "zerolatency",
            "x264-params": "nal-hrd=cbr:force-cfr=1:vbv-maxrate=2500:vbv-bufsize=5000:keyint=60:min-keyint=60:scenecut=0",
        }
        self.audio = self.output.add_stream("aac", rate=RATE)
        self.audio.layout = "mono"
        self.audio.bit_rate = 96000

    def stop_break(self):
        if self._idle_thread is not None:
            self._idle_stop.set()
            self._idle_thread.join()
            self._idle_thread = None

    def start_break(self):
        if self.failed or not self.frames or self._idle_thread is not None:
            return
        self._idle_stop.clear()

        def transmit():
            image = Image.new("RGB", SIZE, INK)
            draw = ImageDraw.Draw(image)
            draw.text((64, 216), "APEX   /   AI GAMING CHARACTER", font=font(34, True), fill=LIME)
            draw.text((64, 288), "Reviewing the replay", font=font(64, True), fill=PAPER)
            draw.text(
                (64, 400), "That round is over. Checking the recording.", font=font(28), fill=PAPER
            )
            frame = av.VideoFrame.from_image(image).reformat(format="yuv420p")
            wave = av.AudioFrame.from_ndarray(
                np.zeros((1, SAMPLES), dtype=np.int16), format="s16", layout="mono"
            )
            wave.sample_rate = RATE
            start = time.monotonic()
            count = 0
            while not self.failed and not self._idle_stop.is_set():
                self._encode(frame, wave)
                count += 1
                self._idle_stop.wait(max(0, start + count / FPS - time.monotonic()))

        self._idle_thread = threading.Thread(target=transmit, name="apex-intermission", daemon=True)
        self._idle_thread.start()

    def write(self, frame, wave):
        self.stop_break()
        self._encode(frame, wave)

    def _encode(self, frame, wave):
        if self.failed:
            return
        try:
            if self.output is None:
                self.start()
            frame.pts = self.frames
            frame.time_base = Fraction(1, FPS)
            wave.pts = self.frames * SAMPLES
            wave.time_base = Fraction(1, RATE)
            self.output.mux(self.video.encode(frame))
            self.output.mux(self.audio.encode(wave))
            self.frames += 1
        except (OSError, ValueError, RuntimeError):
            self.failed = True

    def close(self):
        self.stop_break()
        if self.output is None:
            return
        try:
            if not self.failed:
                self.output.mux(self.video.encode())
                self.output.mux(self.audio.encode())
        except (OSError, ValueError, RuntimeError):
            self.failed = True
        finally:
            try:
                self.output.close()
            except (OSError, ValueError, RuntimeError):
                self.failed = True
