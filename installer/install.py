"""Friendly installer UI plus a testable command-line path. Standard library only."""
from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from deployment import install
from environment import data_root, diagnostics, extension_root
import theme


def native_macos_setup(arguments: list[str]) -> int | None:
    """Older updaters enter here through Python; keep their process tracked."""
    app = Path(__file__).resolve().parents[1] / "CapForge.app"
    if sys.platform != "darwin" or not app.exists():
        return None
    executable = app / "Contents/MacOS/CapForge"
    if app.is_symlink() or executable.is_symlink() or not executable.is_file() or app.resolve() not in executable.resolve().parents:
        raise RuntimeError("The native CapForge Setup application is incomplete. Download the macOS package again.")
    # The previous updater restored execute bits only for .sh and .command.
    executable.chmod(0o755)
    return subprocess.call([str(executable), *arguments], cwd=str(app.parent))


def wizard(target: Path | None = None, extensions: Path | None = None) -> None:
    runtime = target or data_root()
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:
        raise RuntimeError("The setup window is unavailable. Open the CapForge setup launcher again to repair the private runtime.")
    try:
        window = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError(f"The graphical installer could not open: {error}\nOpen CapForge Setup again to retry, or use --headless from a terminal.") from error
    window.title("Install CapForge")
    geometry, wrap = theme.layout(float(window.tk.call("tk", "scaling")))
    window.geometry(geometry)
    window.resizable(False, False)
    window.configure(bg=theme.BACKGROUND)
    fg, muted, accent = theme.TEXT, theme.MUTED, theme.ACCENT
    font = "Segoe UI" if sys.platform == "win32" else "Helvetica"
    pad = tk.Frame(window, bg=theme.BACKGROUND)
    pad.pack(fill="both", expand=True, padx=30, pady=24)
    tk.Label(pad, text="CAPFORGE  /  SETUP", bg=theme.BACKGROUND, fg=accent, font=(font, 10, "bold")).pack(anchor="w")
    tk.Label(pad, text="Make room for your next story.", bg=theme.BACKGROUND, fg=fg, font=(font, 20), justify="left").pack(anchor="w", pady=(12, 8))
    tk.Label(pad, text="Word-timed Georgian and English captions inside After Effects.\nInstalls for your account. No administrator password needed.", bg=theme.BACKGROUND, fg=muted, font=(font, 10), justify="left").pack(anchor="w", pady=(0, 8))
    for name, ready, detail in diagnostics():
        block = tk.Frame(pad, bg=theme.SURFACE)
        block.pack(fill="x", pady=(7, 0))
        tk.Label(block, text=("✓  " if ready else "○  ") + name, bg=theme.SURFACE, fg=accent if ready else fg, font=(font, 10, "bold")).pack(anchor="w", padx=12, pady=(5, 0))
        tk.Label(block, text=detail, bg=theme.SURFACE, fg=muted, font=(font, 9), wraplength=wrap, justify="left").pack(anchor="w", padx=12, pady=(1, 5))
    tk.Label(pad, text="INSTALL LOCATION", bg=theme.BACKGROUND, fg=muted, font=(font, 8)).pack(anchor="w", pady=(16, 5))
    location = tk.Entry(pad, readonlybackground=theme.SURFACE, fg=fg, relief="flat", font=(font, 9))
    location.insert(0, str(runtime))
    location.configure(state="readonly")
    location.pack(fill="x", ipady=6)
    unsigned = tk.BooleanVar(value=True)
    tk.Checkbutton(pad, text="Allow unsigned Adobe extensions for this account (preview build)", variable=unsigned, bg=theme.BACKGROUND, fg=muted, activebackground=theme.BACKGROUND, activeforeground=fg, selectcolor=theme.SURFACE, font=(font, 9), wraplength=wrap, justify="left").pack(anchor="w", pady=(12, 8))
    tk.Label(pad, text="Internet is needed for first setup. Close AE before updating.\nAdd your AI account in the panel’s guided Setup after installation.", bg=theme.BACKGROUND, fg=muted, font=(font, 9), justify="left").pack(anchor="w")
    status = tk.StringVar(value="Ready to install. Your existing projects stay intact.")
    tk.Label(pad, textvariable=status, bg=theme.BACKGROUND, fg=muted, font=(font, 9), wraplength=wrap, height=2, anchor="w", justify="left").pack(fill="x", pady=(10, 0))
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure("CapForge.Horizontal.TProgressbar", background=accent, troughcolor=theme.SURFACE, borderwidth=0, thickness=4)
    progress = ttk.Progressbar(pad, mode="indeterminate", style="CapForge.Horizontal.TProgressbar")
    progress.pack(fill="x", pady=(3, 12))
    events = queue.Queue()
    installed = {"done": False}
    def begin():
        if installed["done"]:
            launcher = runtime / ("run_backend.bat" if sys.platform == "win32" else "run_backend.command")
            if sys.platform == "win32":
                import os
                os.startfile(launcher)
            elif sys.platform == "darwin":
                subprocess.Popen(["/usr/bin/open", str(launcher)])
            return
        button.configure(state="disabled", text="Installing…")
        progress.start(15)
        allow_unsigned = unsigned.get()
        def work():
            try:
                install(runtime, extensions, unsigned=allow_unsigned, progress=lambda message: events.put(("progress", message)))
                events.put(("complete", "Installed. Restart AE → Window → Extensions → CapForge."))
            except Exception as error:
                events.put(("error", str(error)))
        threading.Thread(target=work, daemon=True).start()
    footer = tk.Frame(pad, bg=theme.BACKGROUND)
    footer.pack(fill="x", side="bottom")
    button = tk.Button(footer, text="Install CapForge", command=begin, bg=accent, fg=theme.ACCENT_INK, activebackground=theme.ACCENT_HOVER, activeforeground=theme.ACCENT_INK, font=(font, 10, "bold"), relief="flat", padx=16, pady=5)
    button.pack(side="right")
    def poll():
        while not events.empty():
            kind, message = events.get()
            status.set(message)
            if kind == "complete":
                progress.stop()
                installed["done"] = True
                button.configure(state="normal", text="Start local service")
            elif kind == "error":
                progress.stop()
                button.configure(state="normal", text="Try again")
                messagebox.showerror("Installation needs attention", message)
        window.after(150, poll)
    window.after(150, poll)
    def close():
        if str(button["state"]) == "disabled":
            messagebox.showinfo("Installation in progress", "Let installation finish before closing this window.")
        else:
            window.destroy()
    window.protocol("WM_DELETE_WINDOW", close)
    tk.Button(footer, text="Close", command=close, bg=theme.SURFACE, fg=fg, activebackground=theme.SURFACE, activeforeground=fg, font=(font, 10), relief="flat", padx=16, pady=5).pack(side="left")
    window.mainloop()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install CapForge for the current user.")
    parser.add_argument("--headless", action="store_true", help="Install without the graphical wizard")
    parser.add_argument("--dry-run", action="store_true", help="Show checks and destinations without changing files")
    parser.add_argument("--target", type=Path, help="Custom runtime destination (must be empty or owned)")
    parser.add_argument("--extension-root", type=Path, help="Custom CEP extensions parent")
    parser.add_argument("--skip-dependencies", action="store_true", help="Offline/testing only: do not provision Python packages")
    parser.add_argument("--enable-unsigned", action="store_true", help="Enable Adobe PlayerDebugMode for this unsigned preview build")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"checks": diagnostics(), "runtime": str(args.target or data_root()), "extensions": str(args.extension_root or extension_root()), "enableUnsigned": args.enable_unsigned}, indent=2))
    elif args.headless:
        install(args.target, args.extension_root, dependencies=not args.skip_dependencies, unsigned=args.enable_unsigned)
    else:
        result = native_macos_setup(sys.argv[1:])
        if result is not None:
            return result
        wizard(args.target, args.extension_root)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Installation needs attention: {error}", file=sys.stderr)
        raise SystemExit(1)
