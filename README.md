# Packaging Tool
## Windows
```bash
pyinstaller qanda_downloader.py --name qanda_downloader --onefile --noconsole --icon app_resource\downloader.ico --add-binary=ffmpeg\win\ffmpeg.exe;ffmpeg --paths .
```

## MacOS
```bash
pyinstaller qanda_downloader.py --name qanda_downloader --onefile --windowed --icon app_resource/downloader.icns --add-binary=ffmpeg/mac/ffmpeg:ffmpeg --paths .
```

## Test account
Use this account for testing:
- Email: thanhthuong060606@gmail.com
- Password: 123456