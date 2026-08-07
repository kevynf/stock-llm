from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


project_root = Path(SPECPATH).parent
app_icon = project_root / "src-tauri" / "icons" / "icon.ico"
datas = []
binaries = []
hiddenimports = collect_submodules("keyring.backends")


def is_runtime_submodule(name: str) -> bool:
    parts = name.split(".")
    excluded_parts = {"tests", "test", "demo", "demos", "benchmark", "benchmarks", "conftest"}
    return not excluded_parts.intersection(parts) and not any(part.endswith("_tests") for part in parts)


for package in ("akshare", "baostock", "pyarrow", "pypdf"):
    package_datas, package_binaries, package_hidden = collect_all(
        package,
        include_py_files=False,
        filter_submodules=is_runtime_submodule,
        exclude_datas=["**/tests/**", "**/test/**"],
    )
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    [str(project_root / "packaging" / "desktop_entry.py")],
    pathex=[str(project_root / "backend")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="stockllm-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(app_icon),
)
