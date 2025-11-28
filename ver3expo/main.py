#!/usr/bin/env python3
# coding: utf-8
"""
Quiz Tournament - PySide6 (final integrado)
- Barra de tiempo larga con número decreciente a la derecha
- Logos en fila MEDIANOS debajo de los botones
- 15 preguntas por ronda, pide nombres de equipos antes
- Buzzer + Correcto/Errado + sección + CSV + resource_path
- Botones de respuesta siempre grises
- Fondo del timer gris y barra roja
- Glow rojo alrededor del recuadro de la pregunta
- Diálogo con checkboxes para elegir categorías (incluye opción TODAS)
- Persistencia: guarda preguntas usadas en state.json para evitar repeticiones
- SONIDOS: Añadido sonido de tick y timeout al reloj.
"""
import sys, os, csv, random, json
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QComboBox,
    QMessageBox, QInputDialog, QFileDialog, QProgressBar, QCheckBox,
    QGraphicsDropShadowEffect
)
from PySide6.QtMultimedia import QSoundEffect # <-- IMPORTACIÓN NECESARIA PARA SONIDO

# ---------- Helpers ----------
def resource_path(rel):
    """Resolve path for normal run and PyInstaller (_MEIPASS)."""
    try:
        base = sys._MEIPASS # type: ignore
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, rel)

def load_csv_questions(path):
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    try:
        with p.open(newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for idx, r in enumerate(reader):
                qid = r.get("id") or str(idx+1)
                section = (r.get("section") or r.get("categoria") or "").strip()
                question = (r.get("question") or r.get("pregunta") or "").strip()
                opts = [
                    (r.get("option1") or r.get("A") or "").strip(),
                    (r.get("option2") or r.get("B") or "").strip(),
                    (r.get("option3") or r.get("C") or "").strip(),
                    (r.get("option4") or r.get("D") or "").strip(),
                ]
                correct = (r.get("correct") or r.get("answer") or r.get("respuesta") or "").strip()
                
                if question:
                    rows.append({
                        "id": str(qid),
                        "section": section,
                        "question": question,
                        "options": opts,
                        "correct": correct
                    })
    except Exception as e:
        print("Error loading CSV:", e)
    
    random.shuffle(rows)
    return rows

# ---------- Category Dialog ----------
class CategoryDialog(QtWidgets.QDialog):
    def __init__(self, sections, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleccionar categorías")
        self.resize(360, 480)
        
        layout = QVBoxLayout(self)
        
        title = QLabel("Elige las categorías para esta ronda:")
        title.setWordWrap(True)
        layout.addWidget(title)
        
        # opción TODAS
        self.chk_all = QCheckBox("TODAS")
        self.chk_all.stateChanged.connect(self._toggle_all)
        layout.addWidget(self.chk_all)
        
        # scroll para categorías (por si son muchas)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(6, 6, 6, 6)
        inner_layout.setSpacing(6)

        # checkboxes para cada sección
        self.checks = []
        for s in sections:
            if not s:
                continue
            chk = QCheckBox(s)
            inner_layout.addWidget(chk)
            self.checks.append(chk)
            
        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)
        
        # botones aceptar/cancelar
        btns = QHBoxLayout()
        btn_ok = QPushButton("Aceptar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)
        
    def _toggle_all(self, state):
        checked = state == Qt.Checked
        for chk in self.checks:
            chk.setEnabled(not checked)
            if checked:
                chk.setChecked(False)

    def selected_categories(self):
        if self.chk_all.isChecked():
            return ["TODAS"]
        cats = [chk.text() for chk in self.checks if chk.isChecked()]
        return cats

# ---------- Main Window ----------
class QuizWindow(QMainWindow):
    def __init__(self, csv_file="questions.csv", card_bg="imgs/olimpiada.png"):
        super().__init__()
        self.setWindowTitle("Quiz Tournament - Rondas (15 preguntas)")
        self.resize(1200, 740)
        
        # config
        self.csv_file = Path(csv_file)
        self.card_bg_path = Path(card_bg)
        self.per_round = 60 # preguntas por ronda
        self.seconds_per_question = 1 # valor por defecto de tiempo
        
        # state
        self.all_questions = []
        self.remaining_questions = []
        self.current_round = []
        self.current_index = -1
        self.timer_running = False
        self.remaining_seconds = 0
        
        # sections
        self.sections = []
        self.selected_categories = ["TODAS"]
        
        # teams
        self.teamA_name = "Equipo A"
        self.teamB_name = "Equipo B"
        self.active_team = None
        self.teamA_correct = 0
        self.teamA_wrong = 0
        self.teamB_correct = 0
        self.teamB_wrong = 0
        
        # state file (persistencia)
        self.state_file = Path("state.json")
        self.used_ids = set() # ids de preguntas ya usadas (persistidas)
        
        # team button styles
        self.team_default_style = "background: #d33a2a; color: white; border-radius: 8px; padding: 8px 12px;"
        self.team_selected_style = "background: #ff8a65; color: white; border: 2px solid #fff; border-radius: 8px; padding: 8px 12px;"
        
        # timer
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        
        # Audio effects (NUEVO: Inicialización de objetos de sonido)
        self.tick_sound = QSoundEffect(self)
        self.timeout_sound = QSoundEffect(self)
        self._load_sounds()
        
        # build UI
        self._build_ui()
        
        # load CSV + state
        self._load_questions()
        self._refresh_ui()
        
        # shortcuts
        QtGui.QShortcut(QtGui.QKeySequence("N"), self).activated.connect(self.next_question)
        QtGui.QShortcut(QtGui.QKeySequence("S"), self).activated.connect(self.manual_stop_timer)

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QVBoxLayout(central)
        main.setContentsMargins(16, 12, 16, 12)
        main.setSpacing(8)

        # ----- header with long time bar -----
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(6,6,6,6)
        header_layout.setSpacing(6)

        deco = QFrame()
        deco.setObjectName("headerDeco")
        deco.setFixedHeight(56)
        deco_layout = QHBoxLayout(deco)
        deco_layout.setContentsMargins(14,8,14,8)
        deco_layout.setSpacing(12)
        deco_layout.addStretch()

        self.time_bar = QProgressBar()
        self.time_bar.setRange(0, self.seconds_per_question)
        self.time_bar.setValue(self.seconds_per_question)
        self.time_bar.setTextVisible(False)
        self.time_bar.setFixedHeight(16)
        self.time_bar.setMinimumWidth(700)
        self.time_bar.setMaximumWidth(1100)
        deco_layout.addWidget(self.time_bar, 1, Qt.AlignCenter)

        self.lbl_time_num = QLabel(str(self.seconds_per_question))
        self.lbl_time_num.setFont(QFont("Helvetica", 18, QFont.Bold))
        self.lbl_time_num.setFixedWidth(70)
        self.lbl_time_num.setAlignment(Qt.AlignCenter)
        deco_layout.addWidget(self.lbl_time_num, 0, Qt.AlignRight)
        
        deco_layout.addStretch()
        header_layout.addWidget(deco)
        main.addWidget(header_frame)

        # ----- Imagen banner fuera del recuadro -----
        self.banner_img = QLabel()
        self.banner_img.setAlignment(Qt.AlignCenter)
        
        # --- BLOQUE CORREGIDO: USAR resource_path PARA GARANTIZAR LA CARGA ---
        # 1. Definir la ruta real (usando resource_path)
        banner_path = resource_path(str(self.card_bg_path))

        # 2. Verificar la existencia en la ruta resuelta por resource_path
        if Path(banner_path).exists():
            pix = QPixmap(banner_path)
            if not pix.isNull():
                pix = pix.scaledToWidth(400, Qt.SmoothTransformation)
                self.banner_img.setPixmap(pix)
            else:
                self.banner_img.setText("Error al cargar la imagen: Pixmap nulo")
        else:
            self.banner_img.setText(f"IMAGEN NO ENCONTRADA: {banner_path}")
        # ----------------------------------------------------------------------

        self.banner_img.setFixedHeight(160)
        main.addWidget(self.banner_img)
        
        # ----- main card with glow wrapper -----
        self.card_wrap = QFrame()
        self.card_wrap.setObjectName("questionCardWrap")
        wrap_layout = QVBoxLayout(self.card_wrap)
        wrap_layout.setContentsMargins(10, 10, 10, 10) # margen para que el glow no 
        wrap_layout.setSpacing(0)
        
        self.card = QFrame()
        self.card.setObjectName("questionCard")
        self.card.setMinimumWidth(800)
        self.card.setMinimumHeight(220)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(12,12,12,12)
        card_layout.setSpacing(8)

        # question container
        self.lbl_question = QLabel("Pulsa 'Iniciar Ronda' para comenzar")
        self.lbl_question.setWordWrap(True)
        self.lbl_question.setAlignment(Qt.AlignCenter)
        self.lbl_question.setFont(QFont("Helvetica", 30, QFont.Bold))
        self.lbl_question.setMaximumHeight(200)
        self.lbl_question.setStyleSheet("background: rgba(255,255,255,0.92); color: #202020; padding: 12px; border-radius: 10px;")

        # question counter
        self.lbl_qcounter = QLabel("0 / 0")
        self.lbl_qcounter.setFont(QFont("Helvetica", 11, QFont.Bold))
        self.lbl_qcounter.setStyleSheet("background: rgba(0,0,0,0.45); color: #fff; padding: 6px; border-radius: 6px;")
        self.lbl_qcounter.setAlignment(Qt.AlignCenter)
        self.lbl_qcounter.setFixedSize(68, 28)

        # stacked layout (bg + overlay + counter)
        stack_widget = QWidget()
        stack_layout = QtWidgets.QStackedLayout(stack_widget)
        stack_layout.setStackingMode(QtWidgets.QStackedLayout.StackAll)
        stack_layout.addWidget(self.lbl_question)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(0,0,0,0)
        wrapper.setSpacing(0)
        top_row = QHBoxLayout()
        top_row.addStretch()
        top_row.addWidget(self.lbl_qcounter, alignment=Qt.AlignRight | Qt.AlignTop)
        top_row.setContentsMargins(6,6,6,0)
        wrapper.addLayout(top_row)
        wrapper.addWidget(stack_widget)

        card_layout.addLayout(wrapper)
        
        # añadir card dentro del contenedor con margen y glow
        wrap_layout.addWidget(self.card)
        
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(25)
        glow.setColor(QColor("#d33a2a")) # rojo
        glow.setOffset(0, 0)
        self.card_wrap.setGraphicsEffect(glow)
        
        main.addWidget(self.card_wrap, alignment=Qt.AlignHCenter)

        # ----- answers grid (smaller boxes, always grey) -----
        answers_grid = QGridLayout()
        answers_grid.setHorizontalSpacing(12)
        answers_grid.setVerticalSpacing(12)
        
        self.option_buttons = []
        for i in range(4):
            btn = QPushButton("")
            btn.setObjectName("optionBtn")
            btn.setMinimumHeight(52) # reduced height
            btn.setFont(QFont("Helvetica", 17, QFont.Bold))
            btn.setEnabled(False) # estilo gris inicial
            btn.setStyleSheet("background: #2B2B2B; color: #cfcfcf; border-radius: 8px;")
            self.option_buttons.append(btn)
            
            r = i//2; c = i%2
            answers_grid.addWidget(btn, r, c)
            
        main.addLayout(answers_grid)

        # ----- buzzer row (teams) -----
        buzz_row = QHBoxLayout()
        buzz_row.setSpacing(12)
        
        self.btn_teamA = QPushButton(" ⚡  Equipo A")
        self.btn_teamA.setMinimumHeight(64)
        self.btn_teamA.setFont(QFont("Helvetica", 14, QFont.Bold))
        self.btn_teamA.setStyleSheet(self.team_default_style)
        self.btn_teamA.clicked.connect(lambda: self._set_active_team("A"))
        
        self.btn_teamB = QPushButton(" ⚡  Equipo B")
        self.btn_teamB.setMinimumHeight(64)
        self.btn_teamB.setFont(QFont("Helvetica", 14, QFont.Bold))
        self.btn_teamB.setStyleSheet(self.team_default_style)
        self.btn_teamB.clicked.connect(lambda: self._set_active_team("B"))
        
        buzz_row.addWidget(self.btn_teamA)
        buzz_row.addWidget(self.btn_teamB)
        main.addLayout(buzz_row)

        # ----- scoreboard compact -----
        score_row = QHBoxLayout()
        score_row.setSpacing(12)
        
        self.teamA_box = QFrame()
        ta_l = QVBoxLayout(self.teamA_box)
        self.teamA_lbl = QLabel("Equipo A")
        self.teamA_lbl.setFont(QFont("Helvetica", 14, QFont.Bold))
        self.teamA_score = QLabel("Correctas: 0 Erradas: 0")
        ta_l.addWidget(self.teamA_lbl, alignment=Qt.AlignCenter)
        ta_l.addWidget(self.teamA_score, alignment=Qt.AlignCenter)

        self.teamB_box = QFrame()
        tb_l = QVBoxLayout(self.teamB_box)
        self.teamB_lbl = QLabel("Equipo B")
        self.teamB_lbl.setFont(QFont("Helvetica", 14, QFont.Bold))
        self.teamB_score = QLabel("Correctas: 0 Erradas: 0")
        tb_l.addWidget(self.teamB_lbl, alignment=Qt.AlignCenter)
        tb_l.addWidget(self.teamB_score, alignment=Qt.AlignCenter)

        score_row.addWidget(self.teamA_box)
        score_row.addWidget(self.teamB_box)
        main.addLayout(score_row)

        # ----- bottom controls (buttons) -----
        bottom_controls = QHBoxLayout()
        bottom_controls.setSpacing(12)
        
        left_ctrl = QHBoxLayout()
        self.btn_load = QPushButton("Cargar CSV")
        self.btn_load.clicked.connect(self._cmd_load_csv)
        self.btn_reset = QPushButton("Resetear Progreso") # Botón para borrar el estado JSON
        self.btn_reset.clicked.connect(self._cmd_reset_progress)
        self.btn_start = QPushButton("Iniciar Ronda")
        self.btn_start.clicked.connect(self._start_round_dialog)
        
        # Añade los botones en el orden deseado a left_ctrl
        left_ctrl.addWidget(self.btn_load)
        left_ctrl.addWidget(self.btn_reset) # Ahora Resetear está junto a Cargar CSV
        left_ctrl.addWidget(self.btn_start) # Y luego Iniciar Ronda
        # -------------------------

        bottom_controls.addLayout(left_ctrl)
        bottom_controls.addStretch() # Este stretch empuja todo lo de la izquierda a la izquierda y lo de la derecha a la derecha
        
        right_ctrl = QHBoxLayout()
        self.btn_stop = QPushButton("Detener")
        self.btn_stop.clicked.connect(self.manual_stop_timer)
        self.btn_stop.setEnabled(False)
        
        self.btn_correct = QPushButton("Correcto  ✓ ")
        self.btn_correct.clicked.connect(self._mark_correct)
        self.btn_correct.setEnabled(False)

        self.btn_wrong = QPushButton("Errado  ✕ ")
        self.btn_wrong.clicked.connect(self._mark_wrong)
        self.btn_wrong.setEnabled(False)

        self.btn_next = QPushButton("Siguiente pregunta")
        self.btn_next.clicked.connect(self.next_question)
        self.btn_next.setEnabled(True)
        
        right_ctrl.addWidget(self.btn_stop)
        right_ctrl.addWidget(self.btn_correct)
        right_ctrl.addWidget(self.btn_wrong)
        right_ctrl.addWidget(self.btn_next)
        
        bottom_controls.addLayout(right_ctrl)
        main.addLayout(bottom_controls)

        # ----- logos row (below buttons) - 4 logos medium -----
        logos_row = QHBoxLayout()
        logos_row.setContentsMargins(30, 6, 30, 6)
        logos_row.setSpacing(150)
        logos_row.addStretch()

        for i in range(1,5):
            lbl = QLabel()
            lbl.setFixedSize(180, 110) # medium size
            path = resource_path(f"imgs/logo{i}.png")
            if Path(path).exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    pix = pix.scaled(lbl.width(), lbl.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    lbl.setPixmap(pix)
                else:
                    lbl.setText(f"LOGO{i}")
            else:
                lbl.setText(f"LOGO{i}")
            lbl.setAlignment(Qt.AlignCenter)
            logos_row.addWidget(lbl)
            
        logos_row.addStretch()
        main.addLayout(logos_row)

        # style sheet
        self.setStyleSheet("""
            QMainWindow {
                background: #0b0b0b;
                color: #eee;
            }
            #headerDeco {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1f2833, stop:1 #2b4a6f);
                border-radius: 10px;
            }
            #questionCardWrap {
                background: transparent;
            }
            #questionCard {
                background: #111;
                border-radius: 10px;
            }
            QPushButton {
                background: #d33a2a;
                color: white;
                border-radius: 8px;
                padding: 8px 12px;
            }
            QPushButton#optionBtn {
                background: #2B2B2B;
                color: #cfcfcf;
            }
            QLabel {
                color: #f3f3f3;
            }
            QComboBox {
                background: #222;
                color: #fff;
                padding: 4px;
            }
            QProgressBar {
                background: #2B2B2B;
                border-radius: 8px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #ff8a65, stop:1 #ff3b30);
                border-radius: 8px;
            }
        """)

    # ---------- support methods (persistence) ----------
    def _load_state(self):
        """Carga used_ids desde state.json (si existe)."""
        try:
            if self.state_file.exists():
                data = json.loads(self.state_file.read_text(encoding="utf-8"))
                used = data.get("used", [])
                if isinstance(used, list):
                    self.used_ids = set(str(x) for x in used)
                else:
                    self.used_ids = set()
            else:
                self.used_ids = set()
        except Exception as e:
            print("Error reading state.json:", e)
            self.used_ids = set()

    def _save_state(self):
        """Guarda used_ids en state.json"""
        try:
            data = {"used": sorted(list(self.used_ids))}
            self.state_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("Error writing state.json:", e)
            
    # ---------- support methods (audio) ---------- # <-- NUEVA SECCIÓN PARA SONIDO
    def _load_sounds(self):
        """Carga los archivos de sonido usando resource_path."""
        tick_path = resource_path("sounds/tick.wav")
        timeout_path = resource_path("sounds/timeout.wav")
        
        # Usamos QUrl.fromLocalFile para cargar desde la ruta resuelta
        if Path(tick_path).exists():
            self.tick_sound.setSource(QtCore.QUrl.fromLocalFile(tick_path))
        else:
            print(f"Advertencia: Archivo de sonido tick.wav no encontrado en {tick_path}")
            
        if Path(timeout_path).exists():
            self.timeout_sound.setSource(QtCore.QUrl.fromLocalFile(timeout_path))
        else:
            print(f"Advertencia: Archivo de sonido timeout.wav no encontrado en {timeout_path}")

    # ---------- support methods ----------
    def _load_questions(self):
        qpath = self.csv_file
        if not qpath.exists():
            alt = Path(resource_path(str(self.csv_file)))
            if alt.exists():
                qpath = alt
        
        self.all_questions = load_csv_questions(qpath)
        
        # load saved state (used ids) and build remaining_questions
        self._load_state()
        
        if self.used_ids:
            # filter out used questions
            self.remaining_questions = [q for q in self.all_questions if q.get("id") not in self.used_ids]
        else:
            self.remaining_questions = list(self.all_questions)

        # populate sections
        sections = sorted({(q.get("section") or "").strip() for q in self.all_questions if (q.get("section") or "").strip()})
        self.sections = sections

    def _refresh_ui(self):
        total = len(self.current_round) if self.current_round else 0
        idx = max(0, self.current_index+1) if self.current_round else 0
        self.lbl_qcounter.setText(f"{idx} / {total}")
        
        self.teamA_lbl.setText(self.teamA_name)
        self.teamB_lbl.setText(self.teamB_name)
        self.teamA_score.setText(f"Correctas: {self.teamA_correct} Erradas: {self.teamA_wrong}")
        self.teamB_score.setText(f"Correctas: {self.teamB_correct} Erradas: {self.teamB_wrong}")

        if self.timer_running:
            self.btn_next.setEnabled(False)
        else:
            more = self.current_round and (self.current_index+1 < len(self.current_round))
            self.btn_next.setEnabled(True)

        if not self.timer_running:
            self.time_bar.setRange(0, self.seconds_per_question)
            self.time_bar.setValue(self.seconds_per_question)
            self.lbl_time_num.setText(str(self.seconds_per_question))

    # ---------- round workflow ----------
    def _start_round_dialog(self):
        # elegir categorías con checkboxes
        dlg = CategoryDialog(self.sections, self)
        if dlg.exec() != QtWidgets.QDialog.Accepted:
            return
        
        cats = dlg.selected_categories()
        if not cats:
            QMessageBox.warning(self, "Categorías", "Debe seleccionar al menos una categoría o 'TODAS'.")
            return
        self.selected_categories = cats

        # nombres de equipos
        a, ok = QInputDialog.getText(self, "Nombre Equipo A", "Ingrese nombre del Equipo A:", text="Equipo A")
        if not ok or not a.strip():
            return
        b, ok2 = QInputDialog.getText(self, "Nombre Equipo B", "Ingrese nombre del Equipo B:", text="Equipo B")
        if not ok2 or not b.strip():
            return

        self.teamA_name = a.strip()
        self.teamB_name = b.strip()
        
        self.teamA_correct = self.teamA_wrong = 0
        self.teamB_correct = self.teamB_wrong = 0
        self.active_team = None
        self.generate_round()


    def generate_round(self):
        # Normaliza categorías seleccionadas
        sel = [s.strip().upper() for s in self.selected_categories]

        # 1. Si el usuario selecciona SOLO “TODAS”
        if sel == ["TODAS"]:
            pool = list(self.remaining_questions)
        # 2. Si el usuario selecciona una o más categorías específicas
        else:
            selset = set(sel)
            pool = [
                q for q in self.remaining_questions
                if (q.get("section") or "").strip().upper() in selset
            ]
        
        # 3. Validación estricta de ronda completa
        if len(pool) < self.per_round:
            QMessageBox.warning(
                self, "Preguntas insuficientes",
                f"Quedan {len(pool)} preguntas en las categorías seleccionadas.\n"
                f"Se requieren {self.per_round}."
            )
            return

        # Selección de preguntas
        sample = random.sample(pool, self.per_round)
        ids = {q["id"] for q in sample}

        # Limpiar las usadas
        self.remaining_questions = [
            q for q in self.remaining_questions
            if q["id"] not in ids
        ]
        self.used_ids.update(ids)
        self._save_state()
        
        # Cargar ronda
        self.current_round = sample
        self.current_index = -1
        self.lbl_question.setText("Ronda generada.\nPulsa 'Siguiente pregunta'.")
        self.btn_next.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_correct.setEnabled(False)
        self.btn_wrong.setEnabled(False)
        self._refresh_ui()

    def next_question(self):
        # Si el timer está corriendo, no avanzamos
        if self.timer_running:
            return

        # Si no hay ronda generada
        if not self.current_round:
            QMessageBox.warning(self, "Sin ronda", "No hay una ronda generada.")
            return

        # Avanzar índice
        next_idx = self.current_index + 1

        # Si next_idx >= número de preguntas -> fin de ronda
        if next_idx >= len(self.current_round):
            # Aseguramos detener timer
            self.timer_running = False
            try:
                self.timer.stop()
            except Exception:
                pass

            # Mensaje de fin de ronda con puntajes
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle(" 🎉  Ronda finalizada")
            msg.setText(
                f"La ronda ha terminado.\n\n"
                f"Puntajes:\n"
                f"• {self.teamA_name}: {self.teamA_correct} correctas, {self.teamA_wrong} erradas\n"
                f"• {self.teamB_name}: {self.teamB_correct} correctas, {self.teamB_wrong} erradas\n\n"
                "Pulsa 'Iniciar Ronda' para comenzar otra."
            )
            msg.setIcon(QtWidgets.QMessageBox.Information)
            msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
            msg.exec()

            # Limpiamos la UI y bloqueamos controles
            self.lbl_question.setText("Ronda finalizada.\nPresiona 'Iniciar Ronda'.")
            for b in self.option_buttons:
                b.setText("")
                b.setEnabled(False)
                b.setStyleSheet("background: #2B2B2B; color: #cfcfcf; border-radius: 8px;")
                
            self.btn_next.setEnabled(False)
            self.btn_correct.setEnabled(False)
            self.btn_wrong.setEnabled(False)
            self.btn_stop.setEnabled(False)
            
            # Reset contador visual y estado del índice
            self.lbl_qcounter.setText("0 / 0")
            self.current_index = -1
            return
            
        # Si hay pregunta disponible, asignamos el índice y la mostramos
        self.current_index = next_idx
        q = self.current_round[self.current_index]
        self._display_question(q)

        # Reiniciamos timer y estado
        self.remaining_seconds = self.seconds_per_question
        self.timer_running = True
        self.timer.start()
        self.btn_stop.setEnabled(True)
        self.btn_correct.setEnabled(False)
        self.btn_wrong.setEnabled(False)
        self.active_team = None
        self._refresh_ui()

    def _display_question(self, q):
        self.lbl_question.setText(q.get("question", ""))
        
        # set options
        for i, b in enumerate(self.option_buttons):
            txt = f"{chr(65+i)}) {q['options'][i]}" if i < len(q['options']) and q['options'][i] else ""
            b.setText(txt)
            # reset estilo gris
            b.setStyleSheet("background: #2B2B2B; color: #cfcfcf; border-radius: 8px;")
            b.setEnabled(True)
            
        # timer reset
        self.time_bar.setRange(0, self.seconds_per_question)
        self.time_bar.setValue(self.seconds_per_question)
        self.lbl_time_num.setText(str(self.seconds_per_question))
        
        self._refresh_ui()

    # ---------- timer ----------
    def _tick(self):
        if not self.timer_running:
            return
            
        if self.remaining_seconds <= 0:
            self.timer_running = False
            self.timer.stop()
            self.time_bar.setValue(0)
            self.lbl_time_num.setText("0")
            
            # NUEVO: Reproducir sonido de tiempo agotado
            if self.timeout_sound.isLoaded():
                self.timeout_sound.play()
                
            self._reveal_answer()
            return
            
        # NUEVO: Reproducir sonido de tick en cada segundo
        if self.tick_sound.isLoaded():
            self.tick_sound.play()
            
        # decrement and update bar + numeric label
        self.remaining_seconds -= 1
        self.time_bar.setValue(self.remaining_seconds)
        self.lbl_time_num.setText(str(self.remaining_seconds))

    def manual_stop_timer(self):
        if not self.timer_running:
            return
            
        self.timer_running = False
        self.timer.stop()
        
        # Opcional: Si se detiene manualmente, también se podría reproducir el sonido de "timeout" o un sonido de "stop"
        if self.timeout_sound.isLoaded():
            self.timeout_sound.play() 

        self._reveal_answer()

    def _reveal_answer(self):
        if not self.current_round or self.current_index < 0:
            return
            
        q = self.current_round[self.current_index]
        correct = (q.get("correct") or "").strip().lower()
        
        for i, b in enumerate(self.option_buttons):
            opt = (q.get("options") or [])[i] if i < len(q.get("options", [])) else ""
            
            if opt and correct and opt.strip().lower() == correct:
                b.setStyleSheet("background: #1FB954; color: white; border-radius: 8px;") # verde correcto
            else:
                b.setStyleSheet("background: #2B2B2B; color: #cfcfcf; border-radius: 8px;")

        self.btn_correct.setEnabled(True)
        self.btn_wrong.setEnabled(True)
        self.btn_next.setEnabled(True)
        self.btn_stop.setEnabled(False)

    # ---------- buzzer/team logic ----------
    def _set_active_team(self, team):
        self.active_team = team
        if self.timer_running:
            self.timer_running = False
            self.timer.stop()
            
            # Opcional: Añadir un sonido de "buzzer" aquí
            
        if team == "A":
            self.btn_teamA.setStyleSheet(self.team_selected_style)
            self.btn_teamB.setStyleSheet(self.team_default_style)
        else:
            self.btn_teamB.setStyleSheet(self.team_selected_style)
            self.btn_teamA.setStyleSheet(self.team_default_style)

        self.btn_correct.setEnabled(True)
        self.btn_wrong.setEnabled(True)
        self.btn_next.setEnabled(True)

    def _mark_correct(self):
        if not self.active_team:
            QMessageBox.warning(self, "Sin equipo", "Presiona el buzzer del equipo antes de marcar.")
            return

        if self.active_team == "A":
            self.teamA_correct += 1
        else:
            self.teamB_correct += 1
            
        self._after_marking()

    def _mark_wrong(self):
        if not self.active_team:
            QMessageBox.warning(self, "Sin equipo", "Presiona el buzzer del equipo antes de marcar.")
            return

        if self.active_team == "A":
            self.teamA_wrong += 1
        else:
            self.teamB_wrong += 1
            
        self._after_marking()

    def _after_marking(self):
        # volver ambos al rojo por defecto
        self.btn_teamA.setStyleSheet(self.team_default_style)
        self.btn_teamB.setStyleSheet(self.team_default_style)
        self.active_team = None
        
        self.btn_next.setEnabled(True)
        self.btn_correct.setEnabled(False)
        self.btn_wrong.setEnabled(False)
        self._refresh_ui()

    # ---------- CSV load ----------
    def _cmd_load_csv(self):
        fp, _ = QFileDialog.getOpenFileName(self, "Selecciona questions.csv", filter="CSV files (*.csv);;All files (*)")
        if not fp:
            return

        # preguntar si reiniciar historial de usadas
        resp = QMessageBox.question(self, "Reiniciar historial", "¿Deseas reiniciar el historial de preguntas usadas al cargar este CSV?\n(Si NO, se preservarán las usadas)", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if resp == QMessageBox.Cancel:
            return

        self.csv_file = Path(fp)
        self._load_questions()

        if resp == QMessageBox.Yes:
            # vaciar used_ids y eliminar state.json si existe
            self.used_ids = set()
            try:
                if self.state_file.exists():
                    self.state_file.unlink()
            except Exception as e:
                print("No se pudo borrar state.json:", e)

        # guardar estado actual (por si cambiamos used)
        self._save_state()
        QMessageBox.information(self, "CSV", "CSV cargado correctamente.")
        self._refresh_ui()

    def _cmd_reset_progress(self):
        # 1. Diálogo de confirmación
        reply = QMessageBox.question(self, 'Resetear Progreso', 
                                    "¿Estás seguro de que quieres **resetear el progreso**?\nEsto borrará el archivo quiz_state.json y todas las preguntas estarán disponibles de nuevo.", 
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                # 2. Borrar el archivo de estado
                if self.state_file.exists():
                    os.remove(self.state_file)
                
                # 3. Resetear el estado interno y recargar preguntas
                self.used_ids = set()
                self._load_questions() # Vuelve a cargar todas las preguntas del CSV
                
                # 4. Actualizar la UI
                QMessageBox.information(self, "Progreso Reseteado", "El progreso ha sido reseteado.\nTodas las preguntas están disponibles para la siguiente ronda.")
                self.lbl_question.setText("Progreso reseteado. Pulsa 'Iniciar Ronda'.")
                self.current_round = []
                self.current_index = -1
                self._refresh_ui()
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo borrar el archivo de estado: {e}")

# ---------- run ----------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="questions.csv")
    parser.add_argument("--card_bg", default="imgs/olimpiada.png")
    args = parser.parse_args()
    
    app = QApplication(sys.argv)
    win = QuizWindow(csv_file=args.file, card_bg=args.card_bg)
    win.show()
    sys.exit(app.exec())