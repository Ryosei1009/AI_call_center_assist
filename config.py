"""デモ全体の設定値。動作を調整するときは、まずこのファイルを変更する。"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
DEMO_AUDIO_DIR = BASE_DIR / "demo_audio"  # 録音で発表するときの音声

# --- 音声入力（授業の演習と同じ 16kHz・モノラル・16bit）---
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SAMPLES = 1600  # 0.1秒ごとにマイクから受け取る

# --- 音声区間検出（第15,16回）---
FRAME_MS = 25          # フレーム長
SHIFT_MS = 10          # フレーム間隔
PRE_EMPHASIS = 0.97    # 高域強調 H(z) = 1 - 0.97z^-1
CALIBRATION_SEC = 1.0  # 開始直後に周囲の雑音の大きさを測る時間
POWER_MARGIN_DB = 12.0 # 雑音より何dB大きければ音声とみなすか
ZCR_THRESHOLD = 0.25   # 無声子音を拾うためのゼロ交差率のしきい値
SPEECH_START_MS = 100  # これだけ音声が続いたら発話開始
SPEECH_END_MS = 600    # これだけ無音が続いたら発話終了
PRE_ROLL_MS = 300      # 発話開始の直前も残し、語頭の欠けを防ぐ
MIN_VOICED_MS = 300    # 音声と判定した時間がこれより短ければ雑音として捨てる
MAX_UTTERANCE_SEC = 12.0  # 長い発話はここで区切って文字起こしする

# --- 文字起こし（faster-whisper）---
WHISPER_MODEL = "small"     # 軽くしたいとき: base / 高精度にしたいとき: medium
WHISPER_DEVICE = "cpu"      # NVIDIA GPU が使えるなら "cuda"
WHISPER_COMPUTE_TYPE = "int8"  # cuda のときは "float16"
WHISPER_LANGUAGE = "ja"
WHISPER_BEAM_SIZE = 3
# 商品名のヒントの渡し方（python compare_prompt.py で録音を使って比べられる）
#   "auto"：ヒントなしで認識して商品を判定し、その商品名だけをヒントにもう一度認識する
#   "list"：商品名の一覧をヒントにする（別の商品名に引き寄せられることがある）
#   "none"：ヒントを渡さない（商品名の表記が崩れやすい）
WHISPER_PROMPT_MODE = "auto"
WHISPER_NO_SPEECH_MAX = 0.6  # 「音声なし」の確率がこれ以上の区間は捨てる
WHISPER_LOGPROB_MIN = -1.0   # 認識の自信がこれ以下の区間は捨てる

# --- ワード・スポッティングと検索 ---
SPOTTING_MAX_ERROR_RATE = 0.25  # 語の長さに対して許す誤りの割合
CONFIDENCE_THRESHOLD = 0.55     # これ未満は「候補なし」を表示する
TOP_K = 3                       # 表示する回答候補の数

# --- 画面 ---
# 文字の大きさの倍率。画面の高さから自動で決めた大きさに掛ける。
# 発表中は Ctrl + ; / Ctrl + - で拡大・縮小、Ctrl + 0 で元に戻せる。
UI_SCALE = 1.0
START_MAXIMIZED = True
DEMO_SHOW_SCRIPT = False  # 録音で発表するとき、次の台本と見せる結果を画面に出すか

# --- 目標仕様（レポート表1）---
TARGET_ANSWER_SEC = 10.0
