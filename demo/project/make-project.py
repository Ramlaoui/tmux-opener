"""Create the made-up `vision-lab` project shown in the documentation demos."""

from __future__ import annotations

import io
import json
import math
import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402

INK, PANEL, GRID, TEXT, MUTED = "#0d1117", "#161b22", "#30363d", "#e6edf3", "#8b949e"
GREEN, AMBER, BLUE, PINK = "#3fb950", "#f0b429", "#58a6ff", "#f778ba"
root = Path(sys.argv[1]).expanduser()
random.seed(42)


def write(path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.lstrip("\n"))


def dark_axes(ax) -> None:
    ax.set_facecolor(INK)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.grid(color=GRID, linewidth=0.6, alpha=0.7)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.title.set_color(TEXT)


epochs = list(range(1, 51))
train = [2.3 * math.exp(-e / 11) + 0.18 + random.uniform(-0.03, 0.03) for e in epochs]
val = [2.3 * math.exp(-e / 13) + 0.27 + 0.0016 * max(0, e - 30) ** 1.4 + random.uniform(-0.04, 0.04) for e in epochs]
acc = [min(0.94, 0.42 + 0.5 * (1 - math.exp(-e / 9)) + random.uniform(-0.01, 0.01)) for e in epochs]
lrs = [3e-4 * 0.5 * (1 + math.cos(math.pi * e / 50)) for e in epochs]


def loss_figure(path, upto: int = 50, title: str = "exp-42 · ViT-S/16 on tiny-scenes", dpi: int = 150) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=dpi, facecolor=INK)
    dark_axes(ax)
    ax.plot(epochs[:upto], train[:upto], color=GREEN, linewidth=2.2, label="train loss")
    ax.plot(epochs[:upto], val[:upto], color=AMBER, linewidth=2.2, label="val loss")
    ax.set_xlabel("epoch")
    ax.set_ylabel("cross-entropy")
    ax.set_xlim(1, 50)
    ax.set_ylim(0, 2.4)
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=TEXT)
    legend = ax.legend(frameon=False, labelcolor=TEXT)
    legend.get_frame().set_facecolor(INK)
    fig.tight_layout()
    fig.savefig(path, facecolor=INK)
    plt.close(fig)


def confusion_figure(path: Path) -> None:
    classes = ["beach", "city", "forest", "desert", "snow", "lake"]
    fig, ax = plt.subplots(figsize=(5.5, 5), dpi=150, facecolor=INK)
    dark_axes(ax)
    ax.grid(False)
    matrix = [[random.randint(0, 6) if i != j else random.randint(80, 96) for j in range(6)] for i in range(6)]
    ax.imshow(matrix, cmap="viridis")
    ax.set_xticks(range(6), classes, rotation=40, ha="right")
    ax.set_yticks(range(6), classes)
    for i in range(6):
        for j in range(6):
            ax.text(j, i, matrix[i][j], ha="center", va="center", color=TEXT if matrix[i][j] < 50 else INK, fontsize=9)
    ax.set_title("validation confusion", loc="left", fontweight="bold", color=TEXT)
    fig.tight_layout()
    fig.savefig(path, facecolor=INK)
    plt.close(fig)


def training_gif(path: Path) -> None:
    """The loss curves drawn epoch by epoch, to show the inline viewer playing a GIF."""
    from PIL import Image

    frames = []
    for upto in range(2, 51, 2):
        buffer = io.BytesIO()
        loss_figure(buffer, upto=upto, title=f"exp-42 · epoch {upto}", dpi=100)
        frames.append(Image.open(buffer).convert("RGB"))
    durations = [90] * (len(frames) - 1) + [1500]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0)


def samples_figure(path: Path) -> None:
    fig, axes = plt.subplots(3, 6, figsize=(9, 4.6), dpi=150, facecolor=INK)
    palettes = [("#f6d365", "#3a7bd5"), ("#4b6cb7", "#182848"), ("#56ab2f", "#1e3c12"),
                ("#e8b87d", "#c06c2b"), ("#e0eafc", "#9fb3c8"), ("#2193b0", "#6dd5ed")]
    for index, ax in enumerate(axes.flat):
        top, bottom = palettes[index % 6]
        gradient = [[j / 31 for _ in range(32)] for j in range(32)]
        cmap = matplotlib.colors.LinearSegmentedColormap.from_list("s", [top, bottom])
        ax.imshow(gradient, cmap=cmap)
        for _ in range(4):
            ax.add_patch(plt.Circle((random.uniform(4, 28), random.uniform(10, 28)), random.uniform(1.5, 5),
                                    color=random.choice([GREEN, AMBER, "#ffffff", "#2d333b"]), alpha=0.75))
        ax.set_axis_off()
    fig.suptitle("augmented training samples", color=TEXT, x=0.02, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(path, facecolor=INK)
    plt.close(fig)


def report(path: Path) -> None:
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.1, 0.9, "Scene Classification with Small Vision Transformers", fontsize=17, fontweight="bold")
        fig.text(0.1, 0.87, "vision-lab · weekly report · exp-42", fontsize=11, color="#57606a")
        body = (
            "Abstract. We train a ViT-S/16 on tiny-scenes, a six-class dataset of 48k synthetic\n"
            "landscape images. With RandAugment and a cosine schedule the model reaches 91.3%\n"
            "validation accuracy after 50 epochs. Validation loss starts rising after epoch 30,\n"
            "so we keep the epoch-30 checkpoint and plan stronger regularisation next week.\n\n"
            "1. Setup\n"
            "   - patch size 16, width 384, depth 12, 6 heads\n"
            "   - AdamW, lr 3e-4, weight decay 0.05, batch 256\n"
            "   - 50 epochs on one GPU, about 2 hours\n\n"
            "2. Results\n"
            "   Figure 1 shows the loss curves; Table 1 summarises the best checkpoints."
        )
        fig.text(0.1, 0.55, body, fontsize=10.5, family="DejaVu Sans", va="bottom", linespacing=1.6)
        ax = fig.add_axes((0.1, 0.12, 0.8, 0.36))
        ax.plot(epochs, train, color="#1a7f37", linewidth=2, label="train")
        ax.plot(epochs, val, color="#bf8700", linewidth=2, label="val")
        ax.set_xlabel("epoch")
        ax.set_ylabel("loss")
        ax.grid(alpha=0.3)
        ax.legend(frameon=False)
        fig.text(0.1, 0.07, "Figure 1. Training and validation loss for exp-42.", fontsize=9.5, color="#57606a")
        pdf.savefig(fig)
        plt.close(fig)

        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.1, 0.9, "3. Error analysis", fontsize=14, fontweight="bold")
        ax = fig.add_axes((0.15, 0.45, 0.7, 0.4))
        matrix = [[random.randint(0, 6) if i != j else random.randint(80, 96) for j in range(6)] for i in range(6)]
        ax.imshow(matrix, cmap="Greens")
        classes = ["beach", "city", "forest", "desert", "snow", "lake"]
        ax.set_xticks(range(6), classes, rotation=40, ha="right")
        ax.set_yticks(range(6), classes)
        fig.text(0.1, 0.38, "Most errors confuse snow with desert and lake with beach: both pairs share\n"
                 "large bright regions. Colour jitter will be reduced for the next run.",
                 fontsize=10.5, linespacing=1.6)
        fig.text(0.1, 0.2, "Table 1. Best checkpoints\n\n  epoch   val loss   val acc\n"
                 "    30      0.412     0.903\n    40      0.437     0.911\n    50      0.468     0.913",
                 fontsize=10.5, family="DejaVu Sans Mono", linespacing=1.5)
        pdf.savefig(fig)
        plt.close(fig)


(root / "figures").mkdir(parents=True, exist_ok=True)
loss_figure(root / "figures" / "loss.png")
confusion_figure(root / "figures" / "confusion.png")
samples_figure(root / "figures" / "samples.png")
training_gif(root / "figures" / "training.gif")
(root / "paper").mkdir(exist_ok=True)
report(root / "paper" / "report.pdf")

for run, upto in (("exp-41", 50), ("exp-42", 50)):
    run_dir = root / "runs" / run
    run_dir.mkdir(parents=True, exist_ok=True)
    for epoch in (10, 20, 30, 40, 50):
        loss_figure(run_dir / f"loss_epoch{epoch:03d}.png", upto=epoch, title=f"{run} · epoch {epoch}")
    (run_dir / "metrics.json").write_text(json.dumps(
        {"run": run, "best_epoch": 30, "val_acc": 0.913 if run == "exp-42" else 0.884, "val_loss": 0.412}, indent=2) + "\n")
    (run_dir / "config.yaml").write_text(
        f"run: {run}\nmodel: vit_s16\ndata: tiny-scenes\nepochs: 50\nlr: 3.0e-4\nbatch_size: 256\naugment: randaugment\n")

rows = ["epoch,train_loss,val_loss,val_acc,lr"]
rows += [f"{e},{t:.4f},{v:.4f},{a:.4f},{lr:.2e}" for e, t, v, a, lr in zip(epochs, train, val, acc, lrs)]
write("results/metrics.csv", "\n".join(rows) + "\n")
(root / "checkpoints").mkdir(exist_ok=True)
(root / "checkpoints" / "vit_s16_epoch030.ckpt").write_bytes(random.randbytes(24 * 1024 * 1024))

write("README.md", """
# vision-lab

Small vision transformers for **scene classification** on the tiny-scenes dataset.

## Results

| run    | model    | epochs | val acc |
| ------ | -------- | -----: | ------: |
| exp-41 | ResNet-18 |    50 |  88.4 % |
| exp-42 | ViT-S/16 |     50 |  91.3 % |

## Layout

- `train.py`: training entry point
- `src/vision/`: model and data code
- `runs/`: per-run figures and metrics
- `paper/report.pdf`: the weekly report

## Reproduce

```sh
python train.py --config configs/vit_s16.yaml
```

See the [tmux-opener docs](https://github.com/Ramlaoui/tmux-opener) for how these
files get from the cluster to your laptop.
""")

write("data/scenes-train.csv", "image,label\nscene_0001.jpg,coast\nscene_0002.jpg,forest\nscene_0003.jpg,desert\n")
write("configs/vit_s16.yaml", "model: vit_s16\ndata: tiny-scenes\nepochs: 50\nlr: 3.0e-4\nbatch_size: 256\n")
write("src/vision/__init__.py", "")
write("src/vision/data.py", '''
"""Synthetic tiny-scenes loader."""

CLASSES = ["beach", "city", "forest", "desert", "snow", "lake"]


def batches(batch_size: int, steps: int):
    for step in range(steps):
        yield [[0.0] * 384 for _ in range(batch_size)], [step % len(CLASSES)] * batch_size
''')
write("src/vision/model.py", '''
"""A deliberately tiny stand-in for a ViT-S/16."""

from __future__ import annotations


class PatchEmbedding:
    def __init__(self, patch_size: int = 16, width: int = 384) -> None:
        self.patch_size = patch_size
        self.width = width

    def __call__(self, images):
        return [image[: self.width] for image in images]


class Attention:
    def __init__(self, width: int = 384, heads: int = 6) -> None:
        self.width = width
        self.heads = heads
        self.head_dim = width // heads

    def __call__(self, tokens):
        width = len(tokens[0])
        if width != self.heads * self.head_dim * 2:
            raise ValueError(
                f"qkv projection expects width {self.heads * self.head_dim * 2}, got {width}"
            )
        return tokens


class VisionTransformer:
    def __init__(self, depth: int = 12, width: int = 384, heads: int = 6) -> None:
        self.embed = PatchEmbedding(width=width)
        self.blocks = [Attention(width, heads) for _ in range(depth)]

    def forward(self, images):
        tokens = self.embed(images)
        for block in self.blocks:
            tokens = block(tokens)
        return tokens
''')
write("train.py", '''
"""Train a ViT-S/16 on tiny-scenes (demo: prints a short log, then fails)."""

import sys
import time

sys.path.insert(0, "src")
from vision.data import batches  # noqa: E402
from vision.model import VisionTransformer  # noqa: E402


def log(message: str, pause: float = 0.12) -> None:
    print(message, flush=True)
    time.sleep(pause)


log("\\033[1mvision-lab\\033[0m · run exp-43 · ViT-S/16 · tiny-scenes")
log("docs     https://github.com/Ramlaoui/tmux-opener")
log("notebook http://localhost:8888/?token=7f3a9c")
log("config   configs/vit_s16.yaml")
log("figures  runs/exp-42/loss_epoch050.png")
for epoch in range(1, 4):
    log(f"epoch {epoch:>2}/50  loss {2.31 - 0.4 * epoch:.3f}  acc {0.41 + 0.07 * epoch:.3f}", 0.25)
log("switching to qkv attention with fused projection…")
model = VisionTransformer()
for images, labels in batches(256, 10):
    model.forward(images)
''')
write("notebook/index.html", """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>exp-42 · vision-lab notebook</title>
<style>
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0d1117;color:#e6edf3}
header{padding:18px 28px;border-bottom:1px solid #30363d;display:flex;gap:14px;align-items:center}
.dot{width:12px;height:12px;border-radius:50%;background:#3fb950;box-shadow:0 0 12px #3fb950}
main{padding:28px;display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px}
.k{color:#8b949e;font-size:13px;text-transform:uppercase;letter-spacing:.06em}.v{font-size:34px;font-weight:700}
img{width:100%;border-radius:8px}.amber{color:#f0b429}.green{color:#3fb950}
</style></head><body>
<header><span class="dot"></span><strong>vision-lab notebook</strong><span style="color:#8b949e">running on devbox · port 8888</span></header>
<main>
<div class="card"><div class="k">best val accuracy</div><div class="v green">91.3%</div><div style="color:#8b949e">exp-42 · epoch 50</div></div>
<div class="card"><div class="k">best val loss</div><div class="v amber">0.412</div><div style="color:#8b949e">exp-42 · epoch 30</div></div>
<div class="card" style="grid-column:1/-1"><img src="loss.png" alt="loss curves"></div>
<div class="card"><img src="confusion.png" alt="confusion matrix"></div>
<div class="card"><img src="samples.png" alt="training samples"></div>
</main></body></html>
""")
for name in ("loss.png", "confusion.png", "samples.png"):
    (root / "notebook" / name).write_bytes((root / "figures" / name).read_bytes())
write("notes.md", """
# notes

- val loss rises after epoch 30: try stochastic depth 0.1
- compare the curves: runs/*/loss_epoch050.png
- snow/desert confusion: reduce colour jitter
- ask for a longer GPU allocation next week
""")
