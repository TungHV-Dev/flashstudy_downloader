# Packaging Tool
## Windows
```bash
pyinstaller app.py --name flashstudy_downloader --onefile --noconsole --icon app_resource\downloader.ico --add-binary=ffmpeg\win\ffmpeg.exe;ffmpeg --paths .
```

## MacOS
```bash
pyinstaller app.py --name flashstudy_downloader --onefile --icon app_resource/downloader.icns --add-binary=ffmpeg/mac/ffmpeg:ffmpeg --paths .
```

## Test account
Use this account for testing:
- Phone: 0328229991
- Password: study12345