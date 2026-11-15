"""コールセンター リアルタイム業務支援デモ。実行: python main.py

画面の処理（Tkinter）は1つのスレッドでしか動かせない。そのため時間のかかる
録音と文字起こしは別スレッドで行い、結果をキュー経由で画面へ渡す。

  マイク → 音声区間検出 → [キュー] → 文字起こし → [キュー] → 画面と業務処理
"""
from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

import config
from call_session import CallSession, TurnResult
from faq_search import FaqSearcher

ROLE_LABELS = {"customer": "お客様", "operator": "オペレーター"}
FONT = "Meiryo UI"
INK, BLUE, RED, MUTED, PALE = "#1f2a37", "#1d5fa8", "#b4472a", "#6b7280", "#eaf1f9"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("コールセンター リアルタイム業務支援デモ")
        self.geometry("1180x720")
        self.minsize(980, 620)
        if config.START_MAXIMIZED:
            try:
                self.state("zoomed")  # Windows で最大化して起動する
            except tk.TclError:
                pass
        self._build_fonts()
        self.configure(bg="#f3f4f6")

        self.searcher = FaqSearcher.from_files()
        self.session = CallSession(self.searcher)
        self.role = tk.StringVar(value="customer")
        self.listener = None
        self.utterances: queue.Queue = queue.Queue()
        self.events: queue.Queue = queue.Queue()
        self.transcriber = None
        self.worker_started = False
        self.muted = False
        self.demo_steps = []
        self.demo_index = 0

        self._build_style()
        self._build_header()
        self._build_body()
        self.after(100, self._poll_events)

    # ---------- 画面の組み立て ----------
    def _build_fonts(self):
        """文字の大きさを画面の高さから決める。1080pの画面で本文18ポイント。

        名前付きフォントを使うので、大きさを変えると全ての文字が一度に変わる。
        """
        self.default_size = max(11, round(self.winfo_screenheight() / 60 * config.UI_SCALE))
        self.fonts = {name: tkfont.Font(self, family=FONT, weight=weight)
                      for name, weight in (("small", "normal"), ("body", "normal"),
                                           ("large", "normal"), ("large_bold", "bold"),
                                           ("title", "bold"))}
        self._apply_font_size(self.default_size)
        self.bind_all("<Control-semicolon>", lambda _e: self._apply_font_size(self.font_size + 2))
        self.bind_all("<Control-plus>", lambda _e: self._apply_font_size(self.font_size + 2))
        self.bind_all("<Control-minus>", lambda _e: self._apply_font_size(self.font_size - 2))
        self.bind_all("<Control-Key-0>", lambda _e: self._apply_font_size(self.default_size))

    def _apply_font_size(self, size: int):
        self.font_size = min(max(size, 9), 40)
        ratios = {"small": 0.8, "body": 1.0, "large": 1.15, "large_bold": 1.15, "title": 1.2}
        for name, ratio in ratios.items():
            self.fonts[name].configure(size=round(self.font_size * ratio))
        if hasattr(self, "level"):
            self.level.configure(length=self.font_size * 7)
        if hasattr(self, "transcript"):
            self.transcript.configure(spacing3=self.font_size // 2)

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f4f6")
        style.configure("Card.TFrame", background="white")
        f = self.fonts
        style.configure("TLabel", background="#f3f4f6", foreground=INK, font=f["body"])
        style.configure("Card.TLabel", background="white", foreground=INK, font=f["body"])
        style.configure("Title.TLabel", background="white", foreground=BLUE, font=f["title"])
        style.configure("Red.TLabel", background="white", foreground=RED, font=f["title"])
        style.configure("TButton", font=f["body"], padding=(10, 6))
        style.configure("TRadiobutton", background="#f3f4f6", font=f["body"])
        style.configure("Timing.TLabel", background="white", foreground=INK, font=f["body"])

    def _build_header(self):
        bar = ttk.Frame(self, padding=(12, 10))
        bar.pack(fill="x")
        self.mic_button = ttk.Button(bar, text="● 通話開始", command=self._toggle_mic)
        self.mic_button.pack(side="left")
        self.mute_button = ttk.Button(bar, text="ミュート (Ctrl+M)", command=self._toggle_mute)
        self.mute_button.pack(side="left", padx=(6, 0))
        self.bind_all("<Control-m>", lambda _e: self._toggle_mute())
        self.demo_button = ttk.Button(bar, text="録音で発表", command=self._start_demo)
        self.demo_button.pack(side="left", padx=(6, 0))
        self.next_button = ttk.Button(bar, text="▶ 次の発話 (F5)", command=self._next_demo)
        self.bind_all("<F5>", lambda _e: self._next_demo())
        ttk.Label(bar, text="話している人：").pack(side="left", padx=(18, 4))
        for role, label in ROLE_LABELS.items():
            ttk.Radiobutton(bar, text=label, value=role, variable=self.role).pack(side="left")
        ttk.Label(bar, text="入力レベル").pack(side="left", padx=(18, 4))
        self.level = ttk.Progressbar(bar, length=self.font_size * 7, maximum=60)
        self.level.pack(side="left")
        self.status = ttk.Label(self, text="「通話開始」を押してください。初回はモデルのダウンロードに時間がかかります。",
                                padding=(14, 0, 14, 6), foreground=MUTED)
        self.status.pack(fill="x")

    def _build_body(self):
        body = ttk.Frame(self, padding=(12, 0, 12, 12))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=5, uniform="c")
        body.columnconfigure(1, weight=6, uniform="c")
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)

        left = self._card(body, "① 自動文字起こし", "Title.TLabel")
        left.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 10))
        self.transcript = tk.Text(left, wrap="char", font=self.fonts["large"], relief="flat",
                                  state="disabled", padx=4, pady=4, fg=INK, spacing3=self.font_size // 2)
        self.transcript.tag_configure("customer", foreground=BLUE, font=self.fonts["large_bold"])
        self.transcript.tag_configure("operator", foreground=MUTED, font=self.fonts["large_bold"])
        self.transcript.tag_configure("question", underline=True, foreground=RED)
        self.transcript.pack(fill="both", expand=True)

        typed = ttk.Frame(left, style="Card.TFrame")
        typed.pack(fill="x", pady=(8, 0))
        ttk.Label(typed, text="文字で試す：", style="Card.TLabel").pack(side="left")
        self.typed_text = ttk.Entry(typed, font=self.fonts["body"])
        self.typed_text.pack(side="left", fill="x", expand=True, padx=4)
        self.typed_text.bind("<Return>", lambda _e: self._send_typed())
        ttk.Button(typed, text="送信", command=self._send_typed).pack(side="left")

        self.answer_card = self._card(body, "② 回答候補（確認してから回答）", "Red.TLabel")
        # 発表で見せたい数字なので、見出しの横に置く（上の行だと画面幅によっては切れる）
        self.timing = ttk.Label(self.answer_card.header, style="Timing.TLabel",
                                text=f"表示まで -（目標{config.TARGET_ANSWER_SEC:.0f}秒）")
        self.timing.pack(side="right")
        self.answer_card.grid(row=0, column=1, sticky="nsew", pady=(0, 10))
        self.answers = ttk.Frame(self.answer_card, style="Card.TFrame")
        self.answers.pack(fill="both", expand=True)
        self.answers.bind("<Configure>", self._rewrap)
        self._show_answer_message("質問を検出すると、ここに回答候補を表示します。")

        form_card = self._card(body, "③ 入力フォームへ自動入力", "Title.TLabel")
        form_card.grid(row=1, column=1, sticky="nsew")
        form = ttk.Frame(form_card, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.fields = {}
        for row, name in enumerate(("用件", "対象商品", "結果")):
            ttk.Label(form, text=name, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=3)
            entry = ttk.Entry(form, font=self.fonts["large"])
            entry.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
            self.fields[name] = entry
        buttons = ttk.Frame(form_card, style="Card.TFrame")
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="確認して登録", command=self._register_call).pack(side="right")
        ttk.Button(buttons, text="新しい通話", command=self._reset).pack(side="right", padx=6)

    def _card(self, parent, title, style):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.header = ttk.Frame(card, style="Card.TFrame")
        card.header.pack(fill="x", pady=(0, 6))
        ttk.Label(card.header, text=title, style=style).pack(side="left")
        return card

    # ---------- マイクと文字起こし ----------
    def _toggle_mic(self):
        if self.demo_steps:
            self._stop_demo()
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
            self.mic_button.configure(text="● 通話開始")
            self.level["value"] = 0
            self.status.configure(text="停止しました。")
            return

        from audio_input import MicrophoneListener
        from speech_to_text import Transcriber
        self.mic_button.state(["disabled"])
        self.status.configure(text="文字起こしモデルを読み込んでいます…")
        if self.transcriber is None:
            self.transcriber = Transcriber(self.searcher.vocabulary(), detect_product=self._product_name)
        self.listener = MicrophoneListener(
            self.utterances, on_level=lambda db: self.events.put(("level", db)))
        if self.muted:
            self.listener.muted.set()
        threading.Thread(target=self._load_and_listen, daemon=True).start()

    def _toggle_mute(self):
        self.muted = not self.muted
        if self.listener is not None:
            (self.listener.muted.set if self.muted else self.listener.muted.clear)()
        if self.muted:
            self.mute_button.configure(text="ミュート解除 (Ctrl+M)")
            self.level["value"] = 0
            self.status.configure(text="ミュート中：音声は文字起こしされません。", foreground=RED)
        else:
            self.mute_button.configure(text="ミュート (Ctrl+M)")
            self.status.configure(text="ミュートを解除しました。" if self.listener else
                                  "「通話開始」を押してください。", foreground=MUTED)

    def _product_name(self, text: str) -> str | None:
        product = self.searcher.detect_product(text)
        return product["name"] if product else None

    # ---------- 録音で発表 ----------
    def _start_demo(self):
        if self.demo_steps:
            self._stop_demo()
            return
        from demo_audio import load_steps
        steps = load_steps()
        if not steps:
            messagebox.showinfo("録音で発表", f"{config.DEMO_AUDIO_DIR} に WAV がありません。\n"
                                "先に python record_demo.py で録音してください。")
            return
        if self.listener is not None:
            self._toggle_mic()
        self.demo_steps, self.demo_index = steps, 0
        self._reset()
        self.demo_button.configure(text="録音を終了")
        self.next_button.pack(side="left", padx=(6, 0), after=self.demo_button)
        self.next_button.state(["disabled"])
        self.status.configure(text="文字起こしモデルを読み込んでいます…", foreground=MUTED)
        threading.Thread(target=self._load_for_demo, daemon=True).start()

    def _load_for_demo(self):
        from speech_to_text import Transcriber
        try:
            if self.transcriber is None:
                self.transcriber = Transcriber(self.searcher.vocabulary(), detect_product=self._product_name)
            if self.transcriber.model is None:
                self.transcriber.load()
        except Exception as exc:
            self.events.put(("demo_error", f"モデルの読み込みに失敗しました：{exc}"))
            return
        self.events.put(("demo_ready", None))

    def _stop_demo(self):
        self.demo_steps = []
        self.demo_button.configure(text="録音で発表")
        self.next_button.pack_forget()
        self.status.configure(text="録音での発表を終了しました。", foreground=MUTED)

    def _show_demo_position(self):
        if self.demo_index >= len(self.demo_steps):
            self.status.configure(text="全ての発話を流しました。「録音を終了」で戻れます。")
            self.next_button.state(["disabled"])
            return
        step = self.demo_steps[self.demo_index]
        text = f"次 {self.demo_index + 1}/{len(self.demo_steps)}：{ROLE_LABELS[step.role]}"
        if config.DEMO_SHOW_SCRIPT:  # 映す画面に台本や結果が出ないよう、初期値では出さない
            text += f"「{step.text}」" + (f"　→ {step.point}" if step.point else "")
        self.status.configure(text=text, foreground=MUTED)
        self.next_button.state(["!disabled"])

    def _next_demo(self):
        if not self.demo_steps or self.demo_index >= len(self.demo_steps):
            return
        if "disabled" in self.next_button.state():
            return  # 再生中や文字起こし中は次へ進めない
        step = self.demo_steps[self.demo_index]
        self.demo_index += 1
        self.next_button.state(["disabled"])
        if step.new_call:
            self._reset(keep_status=True)
        self.role.set(step.role)
        self.status.configure(text=f"再生中：{ROLE_LABELS[step.role]}")
        threading.Thread(target=self._play_step, args=(step,), daemon=True).start()

    def _play_step(self, step):
        from demo_audio import play, read_wav
        try:
            raw, params, samples = read_wav(step.path)
            play(raw, params)
            ended_at = time.time()
            self.events.put(("status", "文字起こし中…"))
            text = self.transcriber.transcribe(samples)
        except Exception as exc:
            self.events.put(("demo_error", f"{step.path.name} の処理に失敗しました：{exc}"))
            return
        self.events.put(("demo_text", (text, ended_at, step.role)))

    def _load_and_listen(self):
        try:
            if self.transcriber.model is None:
                self.transcriber.load()
        except Exception as exc:
            self.events.put(("error", f"モデルの読み込みに失敗しました：{exc}"))
            return
        self.listener.start()
        self.events.put(("listening", None))
        if not self.worker_started:  # 文字起こしの担当は1つだけ起動する
            self.worker_started = True
            self._transcribe_loop()

    def _transcribe_loop(self):
        while True:
            utterance = self.utterances.get()
            self.events.put(("status", "文字起こし中…"))
            try:
                text = self.transcriber.transcribe(utterance.samples)
            except Exception as exc:
                self.events.put(("status", f"文字起こしに失敗しました：{exc}"))
                continue
            self.events.put(("text", (text, utterance.ended_at)))

    def _poll_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "level":
                    self.level["value"] = max(0.0, value + 60.0)
                elif kind == "status":
                    self.status.configure(text=value)
                elif kind == "listening":
                    self.mic_button.state(["!disabled"])
                    self.mic_button.configure(text="■ 通話停止")
                    self.status.configure(text="聞き取り中：最初の1秒で周囲の雑音を測っています。"
                                          if not self.muted else "ミュート中：音声は文字起こしされません。")
                elif kind == "error":
                    self.mic_button.state(["!disabled"])
                    self.mic_button.configure(text="● 通話開始")
                    self.listener = None
                    self.status.configure(text=value)
                elif kind == "text":
                    self._handle_text(*value)
                elif kind == "demo_ready":
                    self._show_demo_position()
                elif kind == "demo_text":
                    text, ended_at, role = value
                    self._handle_text(text, ended_at, role)
                    if not text:
                        messagebox.showinfo("録音で発表", "音声を認識できませんでした。録り直してください。")
                    if self.demo_steps:
                        self._show_demo_position()
                elif kind == "demo_error":
                    self.status.configure(text=value, foreground=RED)
                    if self.demo_steps:
                        self.next_button.state(["!disabled"])
        except queue.Empty:
            pass
        if self.listener is not None and self.listener.error is not None:
            self.events.put(("error", f"マイクを開けませんでした：{self.listener.error}"))
        self.after(100, self._poll_events)

    # ---------- 業務処理の結果を画面へ反映 ----------
    def _send_typed(self):
        text = self.typed_text.get().strip()
        if text:
            self.typed_text.delete(0, "end")
            self._handle_text(text, None)

    def _handle_text(self, text: str, ended_at: float | None, role: str | None = None):
        if not text:
            if not self.muted:
                self.status.configure(text="聞き取り中")
            return
        turn = self.session.handle(role or self.role.get(), text, ended_at)
        self._append_transcript(turn)
        self._update_form(turn)
        if turn.search is not None and turn.search.is_question:
            self._show_candidates(turn)
        if self.listener is not None and not self.muted:
            self.status.configure(text="聞き取り中")

    def _append_transcript(self, turn: TurnResult):
        question = turn.search is not None and turn.search.is_question
        self.transcript.configure(state="normal")
        self.transcript.insert("end", ROLE_LABELS[turn.role] + "：", turn.role)
        self.transcript.insert("end", turn.text + "\n", "question" if question else ())
        self.transcript.see("end")
        self.transcript.configure(state="disabled")

    def _update_form(self, turn: TurnResult):
        for name, value in turn.form.as_dict().items():
            if value:
                self._set_field(name, value)

    def _set_field(self, name: str, value: str):
        self.fields[name].delete(0, "end")
        self.fields[name].insert(0, value)

    def _wrap_width(self) -> int:
        """回答欄の幅に合わせて折り返す。"""
        width = self.answers.winfo_width()
        return max(width - 40, 300) if width > 1 else 560

    def _rewrap(self, _event=None):
        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, (tk.Label, ttk.Label)) and str(child.cget("wraplength")) != "0":
                    child.configure(wraplength=self._wrap_width())
                walk(child)
        walk(self.answers)

    def _clear_answers(self):
        for child in self.answers.winfo_children():
            child.destroy()

    def _show_answer_message(self, message: str):
        self._clear_answers()
        ttk.Label(self.answers, text=message, style="Card.TLabel",
                  foreground=MUTED, wraplength=self._wrap_width()).pack(anchor="w")

    def _show_candidates(self, turn: TurnResult):
        search = turn.search
        if not search.confident:
            self._show_answer_message("候補なし：確信度が低いため、マニュアルを手動で確認してください。")
        else:
            self._clear_answers()
            for rank, candidate in enumerate(search.candidates, start=1):
                self._add_candidate(rank, candidate)
        if turn.elapsed_sec is not None:
            mark = "達成" if turn.elapsed_sec <= config.TARGET_ANSWER_SEC else "未達"
            self.timing.configure(
                text=f"表示まで {turn.elapsed_sec:.1f}秒（目標{config.TARGET_ANSWER_SEC:.0f}秒：{mark}）")

    def _add_candidate(self, rank: int, candidate):
        box = tk.Frame(self.answers, bg=PALE if rank == 1 else "white", padx=8, pady=6)
        box.pack(fill="x", pady=(0, 6))
        bg = box["bg"]
        head = f"{rank}. {candidate.product['name']}　確信度 {candidate.score:.2f}"
        tk.Label(box, text=head, bg=bg, fg=MUTED, font=self.fonts["small"]).pack(anchor="w")
        tk.Label(box, text=candidate.faq["answer"], bg=bg, fg=INK, font=self.fonts["large_bold"],
                 wraplength=self._wrap_width(), justify="left").pack(anchor="w")
        row = tk.Frame(box, bg=bg)
        row.pack(fill="x")
        tk.Label(row, text="出典：" + candidate.faq["source"], bg=bg, fg=MUTED,
                 font=self.fonts["small"]).pack(side="left")
        ttk.Button(row, text="この回答を使った", command=self._adopt).pack(side="right")

    def _adopt(self):
        self._set_field("結果", self.session.adopt_answer().result)

    def _register_call(self):
        fields = {name: entry.get().strip() for name, entry in self.fields.items()}
        if not fields["用件"]:
            messagebox.showinfo("確認", "用件が空です。内容を確認してください。")
            return
        path = self.session.save(fields)
        self.status.configure(text=f"登録しました：{path}")
        self._reset(keep_status=True)

    def _reset(self, keep_status: bool = False):
        self.session = CallSession(self.searcher)
        for entry in self.fields.values():
            entry.delete(0, "end")
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        self.transcript.configure(state="disabled")
        self._show_answer_message("質問を検出すると、ここに回答候補を表示します。")
        self.timing.configure(text=f"表示まで -（目標{config.TARGET_ANSWER_SEC:.0f}秒）")
        if not keep_status:
            self.status.configure(text="新しい通話を開始できます。")


if __name__ == "__main__":
    App().mainloop()
