"""Nhận diện engine của game và tìm game đã cài trên Steam."""
from __future__ import annotations

import os
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameInfo:
    root: Path
    engine: str              # rpgmaker_mv | rpgmaker_mz | renpy | unity_mono | unity_il2cpp | unknown...
    label: str               # tên hiển thị của engine
    supported: bool
    exe: Path | None = None
    data_dir: Path | None = None   # RPG Maker: thư mục data ; Ren'Py: thư mục game ; Unity: <Name>_Data
    notes: list[str] = field(default_factory=list)


def _exes(root: Path) -> list[Path]:
    return sorted(p for p in root.glob("*.exe") if not re.search(r"(unins|crash|setup|redist|vc_?redist|dxsetup|UnityCrashHandler)", p.name, re.I))


def detect(path: str | Path) -> GameInfo:
    root = Path(path)
    if root.is_file():
        root = root.parent
    root = root.resolve()

    # ---- RPG Maker MV / MZ
    for data in (root / "www" / "data", root / "data"):
        if (data / "System.json").exists():
            base = data.parent
            mz = (base / "js" / "rmmz_core.js").exists()
            exe = next((e for e in _exes(root) if e.stem.lower() in ("game", "nw")), None) or next(iter(_exes(root)), None)
            return GameInfo(root, "rpgmaker_mz" if mz else "rpgmaker_mv",
                            "RPG Maker MZ" if mz else "RPG Maker MV", True, exe, data)

    # ---- RPG Maker XP / VX / VX Ace
    if list(root.glob("*.rgss*a")) or list(root.glob("*.rgss*")) or (root / "Game.ini").exists() and (root / "Data").exists():
        return GameInfo(root, "rgss", "RPG Maker XP/VX/VX Ace", False,
                        notes=["Engine này chưa được hỗ trợ tự động."])

    # ---- Ren'Py
    if (root / "game").is_dir() and ((root / "renpy").is_dir() or (root / "lib").is_dir()):
        exes = _exes(root)
        pys = {p.stem for p in root.glob("*.py")}
        exe = next((e for e in exes if e.stem in pys), None) or next((e for e in exes if not e.stem.endswith("-32")), None)
        return GameInfo(root, "renpy", "Ren'Py", True, exe, root / "game")

    # ---- Unity
    for d in sorted(root.glob("*_Data")):
        name = d.name[:-5]
        exe = root / f"{name}.exe"
        if (d / "Managed" / "Assembly-CSharp.dll").exists() or (d / "Managed" / "UnityEngine.dll").exists():
            return GameInfo(root, "unity_mono", "Unity (Mono)", True, exe if exe.exists() else None, d)
        if (root / "GameAssembly.dll").exists() or (d / "il2cpp_data").exists():
            return GameInfo(root, "unity_il2cpp", "Unity (IL2CPP)", False, exe if exe.exists() else None, d,
                            notes=["Game Unity dạng IL2CPP chưa được hỗ trợ tự động (cần BepInEx 6)."])

    # ---- khác
    if list(root.glob("*.pck")):
        return GameInfo(root, "godot", "Godot", False, notes=["Godot đóng gói .pck chưa được hỗ trợ tự động."])
    if (root / "data.xp3").exists():
        return GameInfo(root, "kirikiri", "KiriKiri", False, notes=["KiriKiri chưa được hỗ trợ tự động."])
    if (root / "data.win").exists():
        return GameInfo(root, "gamemaker", "GameMaker", False, notes=["GameMaker chưa được hỗ trợ tự động."])
    return GameInfo(root, "unknown", "Không nhận diện được", False,
                    notes=["Hãy chọn đúng thư mục chứa file .exe của game."])


def exe_arch(exe: Path | None) -> str:
    """'x64' hoặc 'x86' dựa trên PE header."""
    try:
        with open(exe, "rb") as f:
            f.seek(0x3C)
            off = struct.unpack("<I", f.read(4))[0]
            f.seek(off + 4)
            machine = struct.unpack("<H", f.read(2))[0]
        return "x86" if machine == 0x14C else "x64"
    except Exception:  # noqa: BLE001
        return "x64"


# ------------------------------------------------------------------ Steam
def steam_libraries() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key, val in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                   (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        roots.append(Path(winreg.QueryValueEx(k, val)[0]))
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"]
    else:
        roots += [Path.home() / ".steam" / "steam", Path.home() / ".local" / "share" / "Steam"]
    libs: list[Path] = []
    for r in roots:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            txt = vdf.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"path"\s+"([^"]+)"', txt):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
        if (r / "steamapps").exists():
            libs.append(r)
    seen, out = set(), []
    for lib in libs:
        k = str(lib).lower()
        if k not in seen and (lib / "steamapps").exists():
            seen.add(k)
            out.append(lib)
    return out


def steam_games() -> list[tuple[str, Path]]:
    games = []
    for lib in steam_libraries():
        for acf in (lib / "steamapps").glob("appmanifest_*.acf"):
            txt = acf.read_text(encoding="utf-8", errors="replace")
            name = re.search(r'"name"\s+"([^"]*)"', txt)
            inst = re.search(r'"installdir"\s+"([^"]*)"', txt)
            if name and inst:
                p = lib / "steamapps" / "common" / inst.group(1)
                if p.exists() and not re.search(r"redistributable|steamworks|proton|runtime", name.group(1), re.I):
                    games.append((name.group(1), p))
    return sorted(games, key=lambda x: x[0].lower())
