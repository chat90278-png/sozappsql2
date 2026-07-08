# SOZAPP SQL2

## Kurulum

Bağımlılıkları kurmak için proje kökünde aşağıdaki komutu çalıştırın:

```bash
pip install -r requirements.txt
```

## Windows release build

STS.exe is built from the checked-in PyInstaller spec:

```bash
pyinstaller --clean --noconfirm STS.spec
```

The release source of truth is `STS.spec`, with `app.py` as the executable entry point and `STS` as the executable name.
