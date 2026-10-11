# 音声文字起こしツール

Python で音声ファイルを文字起こしし、字幕ファイルとして出力する簡易アプリです。

## 機能

- 音声/動画ファイルを選択して文字起こし
- `txt` 形式のタイムスタンプ付き文字起こしを出力
- `srt` 形式の字幕ファイルを出力
- GUI でも CLI でも利用可能

## 必要環境

- Python 3.11 以上
- Windows 10/11

## インストール

```powershell
python -m pip install faster-whisper ctranslate2
```

> このスクリプトには PyAV 19 系向けの互換補正を入れているため、仮想環境を作らずに既存のシステム Python でも動作します。

## 実行方法

### GUI で起動

```powershell
python transcription.py --gui
```

### CLI で起動

```powershell
python transcription.py sample.m4a
```

### 出力先を指定

```powershell
python transcription.py sample.m4a --out-dir .\out
```

## 生成されるファイル

- `sample.txt`
- `sample.srt`

## 注意事項

- 音声ファイルの種類によっては変換に時間がかかります
- 変換結果の精度は音声品質や話者の発話に依存します
- 公開リポジトリに載せる前提では、秘密情報は `.env` などのローカル設定に分離してください
