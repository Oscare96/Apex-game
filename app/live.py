"""Send only an explicitly selected APEX feed to a fixed RTMPS provider endpoint."""

import json
import re
from fractions import Fraction

import av

from .studio import FPS, RATE, SAMPLES, SIZE

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

    def write(self, frame, wave):
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
