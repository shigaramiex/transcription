#!/usr/bin/env python3
"""
音声ファイルを文字起こしするスクリプト。

セットアップ:
    pip install faster-whisper

使い方:
    python transcribe.py meeting.m4a
    python transcription.py meeting.m4a --model medium --out-dir ./out

出力:
    <name>.txt  タイムスタンプ付きの文字起こし
    <name>.srt  字幕形式（動画編集ソフトなどで使える）
"""

import argparse
import os
import sys
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk


def patch_pyav_compat() -> None:
    """faster-whisper 1.x calls av.open(..., metadata_errors="ignore"), but PyAV 19+ removed this argument.
    Ignore the unsupported keyword so the same code keeps working on modern system Python.
    """
    try:
        import av
    except Exception:
        return

    if getattr(av.open, "__name__", "") == "_compat_open":
        return

    original_open = av.open

    def _compat_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return original_open(*args, **kwargs)

    av.open = _compat_open


patch_pyav_compat()


def load_env_file(env_path: Path | None = None) -> None:
    """ローカルの .env を読み込み、未設定の環境変数だけ反映する。"""
    path = env_path or Path(__file__).resolve().with_name(".env")
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def fmt_ts(sec: float, srt: bool = False) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    if srt:
        ms = int((sec - int(sec)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


def detect_device() -> tuple[str, str]:
    """CUDAが使えればGPU、なければCPU(int8)を使う。"""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def transcribe(
    audio: Path,
    model_size: str,
    language: str | None,
) -> list[tuple[float, float, str]]:
    from faster_whisper import WhisperModel

    device, compute_type = detect_device()
    print(f"モデル読み込み中: {model_size} ({device}, {compute_type})", file=sys.stderr)

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio),
        language=language,
        vad_filter=True,
        beam_size=5,
    )
    print(f"言語: {info.language}  長さ: {fmt_ts(info.duration)}", file=sys.stderr)

    results: list[tuple[float, float, str]] = []
    t0 = time.time()
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        results.append((seg.start, seg.end, text))
        pct = seg.end / info.duration * 100 if info.duration else 0
        print(f"\r進捗 {pct:5.1f}%  経過 {time.time() - t0:5.0f}s", end="", file=sys.stderr)
    print(file=sys.stderr)
    return results


def write_outputs(segs: list[tuple[float, float, str]], base: Path) -> str:
    txt_lines = [f"[{fmt_ts(s)}] {t}" for s, _, t in segs]
    base.with_suffix(".txt").write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

    srt_blocks = [
        f"{i}\n{fmt_ts(s, True)} --> {fmt_ts(e, True)}\n{t}\n"
        for i, (s, e, t) in enumerate(segs, 1)
    ]
    base.with_suffix(".srt").write_text("\n".join(srt_blocks), encoding="utf-8")
    return "\n".join(txt_lines)


def launch_gui() -> None:
    root = tk.Tk()
    root.title("音声文字起こし")
    root.geometry("620x260")
    root.minsize(520, 220)

    file_var = tk.StringVar(value="")
    out_dir_var = tk.StringVar(value="")
    model_var = tk.StringVar(value="medium")
    language_var = tk.StringVar(value="ja")
    status_var = tk.StringVar(value="音声ファイルを選んでください")

    def choose_file() -> None:
        selected = filedialog.askopenfilename(
            title="音声ファイルを選択",
            filetypes=[
                ("音声ファイル", "*.mp3;*.wav;*.m4a;*.mp4;*.flac;*.aac"),
                ("すべてのファイル", "*.*"),
            ],
        )
        if selected:
            file_var.set(selected)
            if not out_dir_var.get():
                out_dir_var.set(str(Path(selected).parent))

    def choose_out_dir() -> None:
        selected = filedialog.askdirectory(title="出力先を選択")
        if selected:
            out_dir_var.set(selected)

    def run_transcription() -> None:
        audio_path = Path(file_var.get()).expanduser()
        if not audio_path.exists():
            status_var.set("音声ファイルが選択されていません")
            return

        out_dir = Path(out_dir_var.get()).expanduser() if out_dir_var.get() else audio_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        def worker() -> None:
            try:
                status_var.set("文字起こし中...")
                lang = None if language_var.get() == "auto" else language_var.get()
                segs = transcribe(audio_path, model_var.get(), lang)
                if not segs:
                    raise ValueError("音声からテキストを検出できませんでした")

                base = out_dir / audio_path.stem
                write_outputs(segs, base)
                status_var.set(f"完了: {base.with_suffix('.txt')} / {base.with_suffix('.srt')}")
            except Exception as exc:  # pragma: no cover - GUI feedback only
                status_var.set(f"エラー: {exc}")
            finally:
                start_button.config(state="normal")

        start_button.config(state="disabled")
        threading.Thread(target=worker, daemon=True).start()

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(frame, text="音声ファイル:").grid(row=0, column=0, sticky="w", pady=(0, 6))
    ttk.Entry(frame, textvariable=file_var, width=52).grid(row=0, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(frame, text="参照", command=choose_file).grid(row=0, column=2, sticky="ew")

    ttk.Label(frame, text="出力先:").grid(row=1, column=0, sticky="w", pady=(0, 6))
    ttk.Entry(frame, textvariable=out_dir_var, width=52).grid(row=1, column=1, sticky="ew", padx=(8, 8))
    ttk.Button(frame, text="選択", command=choose_out_dir).grid(row=1, column=2, sticky="ew")

    ttk.Label(frame, text="モデル:").grid(row=2, column=0, sticky="w", pady=(0, 6))
    ttk.Combobox(frame, textvariable=model_var, values=["tiny", "base", "small", "medium", "large-v3"], state="readonly", width=20).grid(row=2, column=1, sticky="w", padx=(8, 8))

    ttk.Label(frame, text="言語:").grid(row=2, column=2, sticky="w", pady=(0, 6))
    ttk.Combobox(frame, textvariable=language_var, values=["ja", "auto"], state="readonly", width=12).grid(row=2, column=3, sticky="w")

    start_button = ttk.Button(frame, text="文字起こし開始", command=run_transcription)
    start_button.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(12, 8))

    ttk.Label(frame, textvariable=status_var, foreground="#1f5f8b").grid(row=4, column=0, columnspan=4, sticky="w")

    frame.columnconfigure(1, weight=1)
    frame.columnconfigure(3, weight=1)
    root.mainloop()


def main(argv: list[str] | None = None) -> None:
    args_list = sys.argv[1:] if argv is None else argv
    if not args_list or args_list[0] in {"--gui", "-g"}:
        launch_gui()
        return

    parser = argparse.ArgumentParser(description="音声の文字起こし")
    parser.add_argument("audio", nargs="?", type=Path, help="音声/動画ファイル（mp3, m4a, wav, mp4 など）")
    parser.add_argument("--model", default="medium", help="Whisperモデル: tiny/base/small/medium/large-v3（既定: medium）")
    parser.add_argument("--language", default="ja", help="言語コード。自動判定させるなら 'auto'")
    parser.add_argument("--out-dir", type=Path, default=None, help="出力先（既定: 音声と同じ場所）")
    parser.add_argument("--gui", action="store_true", help="GUIを起動してファイル選択で文字起こしする")
    args = parser.parse_args(args_list)

    if args.gui or not args.audio:
        launch_gui()
        return

    if not args.audio.exists():
        sys.exit(f"ファイルが見つかりません: {args.audio}")

    out_dir = args.out_dir or args.audio.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / args.audio.stem

    lang = None if args.language == "auto" else args.language
    segs = transcribe(args.audio, args.model, lang)
    if not segs:
        sys.exit("音声からテキストを検出できませんでした")

    transcript = write_outputs(segs, base)
    print(f"文字起こし: {base.with_suffix('.txt')}", file=sys.stderr)
    print(f"字幕: {base.with_suffix('.srt')}", file=sys.stderr)

    _ = transcript


if __name__ == "__main__":
    main()
