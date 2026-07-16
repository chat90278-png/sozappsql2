# SOZAPP SQL2

## Kurulum

Bağımlılıkları kurmak için proje kökünde aşağıdaki komutu çalıştırın:

```bash
pip install -r requirements.txt
```

## Windows release build

STS.exe is built from the checked-in PyInstaller spec:

Before running PyInstaller, refresh the embedded build metadata:

```bash
python scripts/write_build_info.py
```

`src/_build_info.py` keeps `unknown` placeholders in source control; the script replaces them with the current HEAD commit, short commit, and UTC build timestamp.

```bash
pyinstaller --clean --noconfirm STS.spec
```

The release source of truth is `STS.spec`, with `app.py` as the executable entry point and `STS` as the executable name.
