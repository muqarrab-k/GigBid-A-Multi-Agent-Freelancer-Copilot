"""Turn the recorded approve test into docs/images/demo.gif with ffmpeg."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "apps" / "web" / "test-results" / "demo"
GIF = ROOT / "docs" / "images" / "demo.gif"
# slower, cropped, 128-colour palette
FILTER = ("setpts=1.8*PTS,crop=1280:720:0:0,fps=8,scale=960:-1:flags=lanczos,split[a][b];"
          "[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4")


def main() -> None:
    video = next(VIDEOS.rglob("video.webm"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", FILTER, str(GIF)], check=True)
    print(f"wrote {GIF.relative_to(ROOT)} ({GIF.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
