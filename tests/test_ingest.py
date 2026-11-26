"""Exercise the wire protocol against a real, local FFmpeg ingest process."""

import errno
import socket
import subprocess
import time

import av

from app.live import LiveFeed
from app.show import play


def test_rtmp_ingest_receives_audio_and_video(tmp_path):
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    url = f"rtmp://127.0.0.1:{port}/live/acceptance"
    output = tmp_path / "received.flv"
    server = subprocess.Popen(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-listen",
            "1",
            "-i",
            url,
            "-c",
            "copy",
            "-f",
            "flv",
            str(output),
        ],
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError as exc:
                    if exc.errno != errno.EADDRINUSE:
                        raise
                    break
            if server.poll() is not None:
                raise RuntimeError("FFmpeg listener exited")
            time.sleep(0.05)
        else:
            raise RuntimeError("FFmpeg did not start its listener")
        feed = LiveFeed(url)
        try:
            play(tmp_path / "state", 7, feed=feed)
        finally:
            feed.close()
        server.communicate(timeout=10)
        assert server.returncode == 0 and not feed.failed
        with av.open(str(output)) as media:
            assert {s.type for s in media.streams} == {"audio", "video"}
            assert sum(1 for _ in media.decode(video=0)) == feed.frames
    finally:
        if server.poll() is None:
            server.kill()
            server.wait()
