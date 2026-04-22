#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Developped by bro_tiana
"""

from __future__ import annotations

import sys
import os
import errno
import socket
import json
import threading
import time
import base64
from typing import Optional

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QComboBox, QTextEdit,
        QTabWidget, QRadioButton, QButtonGroup, QFrame, QGroupBox,
        QSizePolicy,
    )
    from PyQt5.QtCore  import Qt, pyqtSignal, QObject
    from PyQt5.QtGui   import QTextCursor, QIcon, QPixmap
    PYQT5_OK = True
except ImportError:
    PYQT5_OK = False

try:
    import evdev
    EVDEV_OK = True
except ImportError:
    EVDEV_OK = False

try:
    from Xlib import display as xdisplay, X
    from Xlib.ext import xtest as xtestmod
    XLIB_OK = True
except ImportError:
    XLIB_OK = False

APP_NAME     = "KVMSoft"
APP_VERSION  = "1.2"
DEFAULT_PORT = 55555
DEFAULT_DEV  = "/dev/input/event3"               # FIX 1
EVDEV_OFFSET = 8
CONFIG_PATH  = os.path.expanduser("~/.config/kvmsoft.json")  # FIX 4

C_BG      = "#1e1e2e"
C_SURFACE = "#2a2a3e"
C_ACCENT  = "#7c6af7"
C_GREEN   = "#50fa7b"
C_RED     = "#ff5555"
C_YELLOW  = "#f1fa8c"
C_TEXT    = "#cdd6f4"
C_MUTED   = "#6c7086"
C_BORDER  = "#45475a"


def _draw_keyboard_on_painter(p, f, QColor, QBrush, QPen, Qt_):
    """Dessine le clavier sur le QPainter p avec facteur d'échelle f."""
    def rr(x, y, w, h, rx=6):
        p.drawRoundedRect(int(x*f), int(y*f), int(w*f), int(h*f), rx*f, rx*f)

    p.setPen(QPen(QColor("#5a4cc0"), max(1, int(2*f))))
    p.setBrush(QBrush(QColor("#7c6af7")))
    rr(2, 14, 60, 36)

    p.setPen(Qt_.NoPen)
    p.setBrush(QBrush(QColor("#cdd6f4")))
    for x, y, w, h in [
        (8,20,7,6),(17,20,7,6),(26,20,7,6),(35,20,7,6),(44,20,12,6),
        (8,28,10,6),(20,28,7,6),(29,28,7,6),(38,28,7,6),(47,28,9,6),
        (8,36,14,6),(48,36,8,6),
    ]:
        rr(x, y, w, h, rx=1)

    p.setBrush(QBrush(QColor("#50fa7b")))
    rr(24, 36, 22, 6, rx=1)


def _make_pixmap(size=64):
    """
    Dessine le clavier sur un QImage (CPU, sans X11),
    puis le convertit en QPixmap.
    """
    if not PYQT5_OK:
        return QPixmap()
    try:
        from PyQt5.QtGui  import QPainter, QBrush, QPen, QColor, QImage
        from PyQt5.QtCore import Qt as Qt_

        img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        img.fill(0)                          # transparent

        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        _draw_keyboard_on_painter(p, size / 64.0, QColor, QBrush, QPen, Qt_)
        p.end()

        px = QPixmap.fromImage(img)          # conversion CPU → GPU
        return px
    except Exception as e:
        import sys
        print("[KVMSoft] Erreur icône : {}".format(e), file=sys.stderr)
        return QPixmap()


def _make_icon():
    if not PYQT5_OK:
        return QIcon()
    px = _make_pixmap(128)  
    return QIcon(px)


def _save_icon_file(path, size=128):
    """
    Sauvegarde l'icône en PNG sur disque.
    Utilisé pour : ~/.local/share/icons/kvmsoft.png
    Permet au gestionnaire de fenêtres de trouver l'icône
    même sans setWindowIcon().
    """
    try:
        px = _make_pixmap(size)
        if px.isNull():
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return px.save(path, "PNG")
    except Exception:
        return False



def load_config():
    defaults = {
        "server_ip":   "192.168.1.100",
        "server_bind": "0.0.0.0",       
        "port":        str(DEFAULT_PORT),
        "toggle_key":  "KEY_F12",
        "device":      DEFAULT_DEV,       
    }
    try:
        with open(CONFIG_PATH, "r") as f:
            saved = json.load(f)
        defaults.update(saved)
    except Exception:
        pass
    return defaults


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass



class WorkerSignals(QObject):
    log_message      = pyqtSignal(str, str)
    status_changed   = pyqtSignal(str, str)
    transfer_changed = pyqtSignal(bool)



class ServerWorker(threading.Thread):

    def __init__(self, host, port, signals):
        super(ServerWorker, self).__init__(daemon=True)
        self.host      = host
        self.port      = port
        self.signals   = signals
        self._stop_evt = threading.Event()
        self._srv_sock = None 

    def log(self, msg, level="info"):
        self.signals.log_message.emit("[SERVEUR] " + msg, level)

    def stop(self):
        self._stop_evt.set()
        if self._srv_sock:
            try:
                self._srv_sock.close()
            except Exception:
                pass

    def run(self):
        if not XLIB_OK:
            self.log("python-xlib non installé — injection impossible.", "error")
            self.signals.status_changed.emit("server", "error")
            return

        try:
            disp = xdisplay.Display()
            if not disp.query_extension("XTEST"):
                self.log("XTEST indisponible. Lancez avec DISPLAY=:0", "error")
                self.signals.status_changed.emit("server", "error")
                return
            self.log("X11 connecté, XTEST disponible.")
        except Exception as ex:
            self.log("Impossible de se connecter à X11 : {}".format(ex), "error")
            self.signals.status_changed.emit("server", "error")
            return

        self._srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            self._srv_sock.bind((self.host, self.port))
            self._srv_sock.listen(1)
            self._srv_sock.settimeout(1.0)
            self.log("En écoute sur {}:{}…".format(self.host, self.port))
            self.signals.status_changed.emit("server", "listening")
        except OSError as ex:
            self.log("Impossible d'écouter sur {}:{} — {}".format(self.host, self.port, ex), "error")
            self.signals.status_changed.emit("server", "error")
            return

        while not self._stop_evt.is_set():
            try:
                conn, addr = self._srv_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            self.log("Client connecté depuis {}".format(addr[0]))
            self.signals.status_changed.emit("server", "connected")

            try:
                disp.change_keyboard_control(auto_repeat_mode=X.AutoRepeatModeOff)
                disp.flush()
                self.log("Autorepeat X11 désactivé (anti-répétition réseau).")
            except Exception as ex:
                self.log("Impossible de désactiver autorepeat : {}".format(ex), "warn")

            self._handle_client(conn, disp)

            try:
                disp.change_keyboard_control(auto_repeat_mode=X.AutoRepeatModeOn)
                disp.flush()
                self.log("Autorepeat X11 restauré.")
            except Exception:
                pass

            self.log("Client déconnecté. En attente…")
            self.signals.status_changed.emit("server", "listening")

        disp.close()
        self.log("Arrêté.")
        self.signals.status_changed.emit("server", "stopped")

    def _handle_client(self, conn, disp):
        enfoncees = set()
        buf = ""
        conn.settimeout(1.0)

        while not self._stop_evt.is_set():
            try:
                data = conn.recv(4096).decode("utf-8")
                if not data:
                    break
                buf += data
                while "\n" in buf:
                    ligne, buf = buf.split("\n", 1)
                    ligne = ligne.strip()
                    if not ligne:
                        continue
                    try:
                        evt   = json.loads(ligne)
                        code  = evt["code"]
                        value = evt["value"]
                        x11   = code + EVDEV_OFFSET
                        if value == 1:
                            if code in enfoncees:
                                continue
                            enfoncees.add(code)
                            xtestmod.fake_input(disp, X.KeyPress, x11)
                        elif value == 0:
                            enfoncees.discard(code)
                            xtestmod.fake_input(disp, X.KeyRelease, x11)
                        disp.flush()
                    except (ValueError, KeyError):
                        pass
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                break

        for code in list(enfoncees):
            xtestmod.fake_input(disp, X.KeyRelease, code + EVDEV_OFFSET)
        disp.flush()
        enfoncees.clear()
        try:
            conn.close()
        except Exception:
            pass



class ClientWorker(threading.Thread):

    def __init__(self, remote_ip, port, device_path, toggle_key, signals):
        super(ClientWorker, self).__init__(daemon=True)
        self.remote_ip   = remote_ip
        self.port        = port
        self.device_path = device_path
        self.toggle_key  = toggle_key
        self.signals     = signals
        self._stop_evt   = threading.Event()
        self._actif      = True

    def log(self, msg, level="info"):
        self.signals.log_message.emit("[CLIENT] " + msg, level)

    def stop(self):
        self._stop_evt.set()

    def _grab(self, clavier):

        try:
            clavier.grab()
            self.log("Mode exclusif actif (grab OK).")
            return True
        except OSError as ex:
            if ex.errno == errno.EBUSY:   # 16 = Device or resource busy
                self.log(
                    "Périphérique occupé (errno 16 EBUSY).\n"
                    "          → Mode non-exclusif : touches envoyées ET tapées localement.\n"
                    "          → Pour le mode exclusif, relancez avec sudo.",
                    "warn"
                )
                return False
            raise   
    def _ungrab(self, clavier):
        try:
            clavier.ungrab()
        except Exception:
            pass

    def _connecter(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.signals.status_changed.emit("client", "connecting")
        while not self._stop_evt.is_set():
            try:
                self.log("Connexion à {}:{}…".format(self.remote_ip, self.port))
                sock.connect((self.remote_ip, self.port))
                self.log("Connecté au serveur !")
                self.signals.status_changed.emit("client", "connected")
                return sock
            except ConnectionRefusedError:
                self.log("Serveur non joignable, nouvel essai dans 3 s…", "warn")
                time.sleep(3)
            except OSError as ex:
                self.log("Erreur réseau : {}".format(ex), "error")
                time.sleep(3)
        return None

    def run(self):
        if not EVDEV_OK:
            self.log("python-evdev non installé.", "error")
            self.signals.status_changed.emit("client", "error")
            return

        try:
            clavier = evdev.InputDevice(self.device_path)
        except Exception as ex:
            self.log("Impossible d'ouvrir {} : {}".format(self.device_path, ex), "error")
            self.log("Relancez avec sudo  —  ou :  sudo usermod -aG input $USER", "warn")
            self.signals.status_changed.emit("client", "error")
            return

        try:
            toggle_code = getattr(evdev.ecodes, self.toggle_key)
        except AttributeError:
            self.log("Touche inconnue : {} → KEY_F12 utilisé.".format(self.toggle_key), "warn")
            toggle_code = evdev.ecodes.KEY_F12

        sock = self._connecter()
        if sock is None:
            return

        self.log("Périphérique : {}  ({})".format(self.device_path, clavier.name))
        self.log("Touche de bascule : {}".format(self.toggle_key))

        exclusive = self._grab(clavier)   # FIX 2
        self._actif = True
        self.signals.transfer_changed.emit(True)
        self.log("✅ Transfert ACTIVÉ")

        try:
            for event in clavier.read_loop():
                if self._stop_evt.is_set():
                    break
                if event.type != evdev.ecodes.EV_KEY:
                    continue

                # Bascule ON/OFF
                if event.code == toggle_code and event.value == 1:
                    self._actif = not self._actif
                    if self._actif:
                        if exclusive:
                            try:
                                clavier.grab()
                            except OSError as ex:
                                if ex.errno == errno.EBUSY:
                                    self.log("Re-grab impossible (errno 16) — toujours en mode non-exclusif.", "warn")
                                    exclusive = False
                        self.log("✅ Transfert ACTIVÉ ({})".format(self.toggle_key))
                    else:
                        if exclusive:
                            self._ungrab(clavier)
                        self.log("⏸  Transfert DÉSACTIVÉ ({}) — frappe locale".format(self.toggle_key))
                    self.signals.transfer_changed.emit(self._actif)
                    continue

                if event.value == 2:  
                    continue

                if self._actif:
                    msg = json.dumps({"code": event.code, "value": event.value}) + "\n"
                    try:
                        sock.sendall(msg.encode("utf-8"))
                    except BrokenPipeError:
                        self.log("Connexion perdue avec le serveur.", "error")
                        self.signals.status_changed.emit("client", "disconnected")
                        break

        except Exception as ex:
            self.log("Erreur inattendue : {}".format(ex), "error")
        finally:
            if exclusive:
                self._ungrab(clavier)
            try:
                sock.close()
            except Exception:
                pass
            self.signals.transfer_changed.emit(False)
            self.log("Arrêté.")
            self.signals.status_changed.emit("client", "stopped")



STYLESHEET = """
QMainWindow, QWidget#central {{
    background-color: {bg};
}}
QWidget {{
    background-color: {bg};
    color: {text};
    font-family: 'Ubuntu', 'DejaVu Sans', sans-serif;
    font-size: 10pt;
}}
QGroupBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 6px;
    margin-top: 8px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
    color: {accent};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}}
QLineEdit, QComboBox {{
    background-color: {bg};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {accent};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QPushButton#btn_start {{
    background-color: {green};
    color: #1e1e2e;
    border: none;
    border-radius: 6px;
    padding: 10px 32px;
    font-size: 13pt;
    font-weight: bold;
    min-width: 180px;
}}
QPushButton#btn_start:hover {{ background-color: #69e07a; }}
QPushButton#btn_stop {{
    background-color: {red};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 10px 32px;
    font-size: 13pt;
    font-weight: bold;
    min-width: 180px;
}}
QPushButton#btn_stop:hover {{ background-color: #ff7070; }}
QPushButton#btn_refresh, QPushButton#btn_clear {{
    background-color: {border};
    color: {text};
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
}}
QRadioButton {{
    color: {text};
    spacing: 6px;
    padding: 4px 10px;
}}
QRadioButton::indicator {{
    width: 14px; height: 14px;
    border: 2px solid {border};
    border-radius: 7px;
    background: {bg};
}}
QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 4px;
    background: {bg};
}}
QTabBar::tab {{
    background: {surface};
    color: {muted};
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}
QTabBar::tab:selected {{ background: {accent}; color: white; }}
QTextEdit {{
    background-color: #11111b;
    color: {text};
    border: none;
    border-radius: 4px;
    font-family: 'Ubuntu Mono', 'DejaVu Sans Mono', monospace;
    font-size: 9pt;
}}
QScrollBar:vertical {{
    background: {surface}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {border}; border-radius: 4px; min-height: 20px;
}}
QLabel#status_ok   {{ color: {green};  font-weight: bold; }}
QLabel#status_err  {{ color: {red};    font-weight: bold; }}
QLabel#status_warn {{ color: {yellow}; font-weight: bold; }}
QLabel#status_off  {{ color: {muted};  }}
QFrame#header      {{ background-color: {accent}; }}
QLabel#header_title {{
    background-color: {accent};
    color: white; font-size: 16pt; font-weight: bold;
}}
QLabel#header_sub {{
    background-color: {accent}; color: #ddd6fe; font-size: 9pt;
}}
QFrame#statusbar   {{ background-color: {surface}; }}
QLabel#statusbar_lbl {{
    background-color: {surface}; color: {muted}; font-size: 8pt;
}}
""".format(
    bg=C_BG, surface=C_SURFACE, accent=C_ACCENT,
    green=C_GREEN, red=C_RED, yellow=C_YELLOW,
    text=C_TEXT, muted=C_MUTED, border=C_BORDER,
)



class KVMSoftWindow(QMainWindow):

    def __init__(self):
        super(KVMSoftWindow, self).__init__()
        self.setWindowTitle("{} {}".format(APP_NAME, APP_VERSION))
        self.resize(740, 660)
        self.setMinimumSize(600, 520)
        self.setStyleSheet(STYLESHEET)
        icon_path = os.path.expanduser("~/.local/share/icons/kvmsoft.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            self.setWindowIcon(_make_icon())

        self.signals       = WorkerSignals()
        self.server_worker = None  
        self.client_worker = None  
        self.running       = False
        self.cfg           = load_config()   

        self._build_ui()
        self._connect_signals()
        self._refresh_devices()



    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(8)
        bl.addWidget(self._make_mode_selector())

        self.tabs = QTabWidget()
        bl.addWidget(self.tabs, 1)

        cfg_tab = QWidget()
        self.tabs.addTab(cfg_tab, "⚙  Configuration")
        self._build_config_tab(cfg_tab)

        log_tab = QWidget()
        self.tabs.addTab(log_tab, "📋  Journal")
        self._build_log_tab(log_tab)

        help_tab = QWidget()
        self.tabs.addTab(help_tab, "❓  Aide")
        self._build_help_tab(help_tab)

        root.addWidget(body, 1)
        root.addWidget(self._make_statusbar())

    def _make_header(self):
        frame = QFrame()
        frame.setObjectName("header")
        frame.setFixedHeight(58)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)


        icon_lbl = QLabel()
        icon_lbl.setObjectName("header_title")
        from PyQt5.QtCore import Qt as _Qt2
        pix = _make_pixmap(64).scaled(38, 38, _Qt2.KeepAspectRatio, _Qt2.SmoothTransformation)
        if not pix.isNull():
            icon_lbl.setPixmap(pix)
        else:
            icon_lbl.setText("⌨")
        lay.addWidget(icon_lbl)

        title = QLabel(APP_NAME)
        title.setObjectName("header_title")
        lay.addWidget(title)

        sub = QLabel("v{}  —  Partage de clavier réseau".format(APP_VERSION))
        sub.setObjectName("header_sub")
        lay.addWidget(sub)
        lay.addStretch()
        return frame

    def _make_mode_selector(self):
        box = QGroupBox("Mode de fonctionnement")
        lay = QHBoxLayout(box)

        self.radio_server = QRadioButton("🖥  Serveur\n(reçoit les touches)")
        self.radio_client = QRadioButton("💻  Client\n(envoie les touches)")
        self.radio_client.setChecked(True)

        self.mode_group = QButtonGroup()
        for rb in (self.radio_server, self.radio_client):
            self.mode_group.addButton(rb)
            lay.addWidget(rb)

        self.radio_server.toggled.connect(self._on_mode_change)
        return box

    def _build_config_tab(self, parent):
        lay = QVBoxLayout(parent)
        lay.setSpacing(8)

        net_box = QGroupBox("🌐  Réseau")
        net_lay = QVBoxLayout(net_box)
        LW = 200   

        row_ip = QHBoxLayout()
        l = QLabel("IP serveur distant :")
        l.setFixedWidth(LW)
        row_ip.addWidget(l)
        self.input_ip = QLineEdit(self.cfg.get("server_ip", "192.168.1.100"))
        self.input_ip.setToolTip("IP du PC qui joue le rôle de serveur (mode client)")
        row_ip.addWidget(self.input_ip)
        net_lay.addLayout(row_ip)

        row_bind = QHBoxLayout()
        l2 = QLabel("Adresse d'écoute serveur :")
        l2.setFixedWidth(LW)
        row_bind.addWidget(l2)
        self.input_bind = QLineEdit(self.cfg.get("server_bind", "0.0.0.0"))
        self.input_bind.setToolTip(
            "Interface d'écoute du serveur.\n"
            "0.0.0.0 = toutes les interfaces (recommandé)\n"
            "127.0.0.1 = localhost uniquement"
        )
        row_bind.addWidget(self.input_bind)
        net_lay.addLayout(row_bind)

        row_port = QHBoxLayout()
        l3 = QLabel("Port TCP :")
        l3.setFixedWidth(LW)
        row_port.addWidget(l3)
        self.input_port = QLineEdit(self.cfg.get("port", str(DEFAULT_PORT)))
        self.input_port.setToolTip("Port réseau (défaut 55555)")
        row_port.addWidget(self.input_port)
        net_lay.addLayout(row_port)

        lay.addWidget(net_box)

        self.client_box = QGroupBox("⌨  Client — Clavier local")
        cli_lay = QVBoxLayout(self.client_box)

        row_dev = QHBoxLayout()
        l4 = QLabel("Périphérique :")
        l4.setFixedWidth(LW)
        row_dev.addWidget(l4)
        self.combo_device = QComboBox()
        self.combo_device.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_device.setEditable(True)
        row_dev.addWidget(self.combo_device, 1)
        btn_ref = QPushButton("↺")
        btn_ref.setObjectName("btn_refresh")
        btn_ref.setFixedWidth(32)
        btn_ref.setToolTip("Rafraîchir la liste des claviers détectés")
        btn_ref.clicked.connect(self._refresh_devices)
        row_dev.addWidget(btn_ref)
        cli_lay.addLayout(row_dev)

        row_tgl = QHBoxLayout()
        l5 = QLabel("Touche de bascule :")
        l5.setFixedWidth(LW)
        row_tgl.addWidget(l5)
        self.input_toggle = QLineEdit(self.cfg.get("toggle_key", "KEY_F12"))
        self.input_toggle.setToolTip(
            "Touche pour activer/désactiver le transfert.\n"
            "Exemples : KEY_F12  KEY_SCROLLLOCK  KEY_PAUSE"
        )
        row_tgl.addWidget(self.input_toggle)
        cli_lay.addLayout(row_tgl)

        lay.addWidget(self.client_box)

        st_box = QGroupBox("📊  État en temps réel")
        st_lay = QVBoxLayout(st_box)

        def status_row(label_text):
            r = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(160)
            r.addWidget(lbl)
            val = QLabel("● Arrêté")
            val.setObjectName("status_off")
            r.addWidget(val)
            r.addStretch()
            st_lay.addLayout(r)
            return val

        self.lbl_srv      = status_row("Serveur :")
        self.lbl_cli      = status_row("Client :")
        self.lbl_transfer = status_row("Transfert clavier :")

        lay.addWidget(st_box)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_start = QPushButton("▶  Démarrer")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.clicked.connect(self._toggle_service)
        btn_row.addWidget(self.btn_start)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        lay.addStretch()

    def _build_log_tab(self, parent):
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(4, 4, 4, 4)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        lay.addWidget(self.log_text, 1)
        btn_clear = QPushButton("🗑  Effacer le journal")
        btn_clear.setObjectName("btn_clear")
        btn_clear.clicked.connect(self.log_text.clear)
        lay.addWidget(btn_clear, 0, Qt.AlignRight)

    def _build_help_tab(self, parent):
        lay = QVBoxLayout(parent)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(HELP_TEXT)
        lay.addWidget(txt)

    def _make_statusbar(self):
        frame = QFrame()
        frame.setObjectName("statusbar")
        frame.setFixedHeight(26)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 0, 12, 0)

        self.lbl_status = QLabel("{} {}  |  Prêt".format(APP_NAME, APP_VERSION))
        self.lbl_status.setObjectName("statusbar_lbl")
        lay.addWidget(self.lbl_status)

        warns = []
        if not EVDEV_OK:
            warns.append("⚠ evdev manquant")
        if not XLIB_OK:
            warns.append("⚠ python-xlib manquant")
        if warns:
            w = QLabel("  |  " + "  ".join(warns))
            w.setStyleSheet("color: {};".format(C_YELLOW))
            w.setObjectName("statusbar_lbl")
            lay.addWidget(w)

        lay.addStretch()

        cfg_lbl = QLabel("Config : {}".format(CONFIG_PATH))
        cfg_lbl.setObjectName("statusbar_lbl")
        lay.addWidget(cfg_lbl)
        return frame


    def _connect_signals(self):
        self.signals.log_message.connect(self._append_log)
        self.signals.status_changed.connect(self._update_status)
        self.signals.transfer_changed.connect(self._set_transfer)



    def _on_mode_change(self):
        self.client_box.setVisible(not self.radio_server.isChecked())

    def _refresh_devices(self):
        """
        FIX 1 : sélectionne /dev/input/event3 par défaut si disponible,
                 sinon utilise la valeur mémorisée dans la config.
        """
        saved_device = self.cfg.get("device", DEFAULT_DEV)
        self.combo_device.clear()

        if not EVDEV_OK:
            self.combo_device.addItem("(evdev non disponible)")
            return

        items = []
        for path in sorted(evdev.list_devices()):
            try:
                d = evdev.InputDevice(path)
                if evdev.ecodes.EV_KEY in d.capabilities():
                    items.append("{} — {}".format(path, d.name))
            except Exception:
                pass

        if not items:
            self.combo_device.addItem("(aucun clavier détecté — lancez avec sudo)")
            return

        self.combo_device.addItems(items)

        for preferred in (DEFAULT_DEV, saved_device):
            for i in range(self.combo_device.count()):
                if self.combo_device.itemText(i).startswith(preferred):
                    self.combo_device.setCurrentIndex(i)
                    return

        self.combo_device.setCurrentIndex(0)

    def _get_device_path(self):
        val = self.combo_device.currentText()
        return val.split(" — ")[0].strip() if " — " in val else val.strip()

    def _toggle_service(self):
        if not self.running:
            self._start()
        else:
            self._stop()

    def _start(self):
        try:
            port = int(self.input_port.text().strip())
        except ValueError:
            self._append_log("[APP] Port invalide.", "error")
            return

        self.cfg.update({
            "server_ip":   self.input_ip.text().strip(),
            "server_bind": self.input_bind.text().strip(),
            "port":        str(port),
            "toggle_key":  self.input_toggle.text().strip(),
            "device":      self._get_device_path(),
        })
        save_config(self.cfg)

        bind = self.input_bind.text().strip() or "0.0.0.0"

        if self.radio_server.isChecked():
            self.server_worker = ServerWorker(bind, port, self.signals)
            self.server_worker.start()

        if self.radio_client.isChecked():
            self.client_worker = ClientWorker(
                remote_ip=self.input_ip.text().strip(),
                port=port,
                device_path=self._get_device_path(),
                toggle_key=self.input_toggle.text().strip(),
                signals=self.signals,
            )
            self.client_worker.start()

        self.running = True
        self.btn_start.setText("⏹  Arrêter")
        self.btn_start.setObjectName("btn_stop")
        self.setStyleSheet(STYLESHEET)

        mode = "serveur" if self.radio_server.isChecked() else "client"
        self.lbl_status.setText("{}  |  En cours — MODE {}".format(APP_NAME, mode.upper()))
        self._append_log("[APP] Service démarré (mode {}).".format(mode), "good")

    def _stop(self):
        if self.server_worker:
            self.server_worker.stop()
            self.server_worker = None
        if self.client_worker:
            self.client_worker.stop()
            self.client_worker = None

        self.running = False
        self.btn_start.setText("▶  Démarrer")
        self.btn_start.setObjectName("btn_start")
        self.setStyleSheet(STYLESHEET)
        self._update_status("server", "stopped")
        self._update_status("client", "stopped")
        self._set_transfer(False)
        self.lbl_status.setText("{}  |  Arrêté".format(APP_NAME))
        self._append_log("[APP] Service arrêté.", "warn")



    def _append_log(self, msg, level="info"):
        colors = {"info": C_TEXT, "warn": C_YELLOW, "error": C_RED, "good": C_GREEN}
        color = colors.get(level, C_TEXT)
        ts    = time.strftime("%H:%M:%S")
        safe  = (msg.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace("\n", "<br>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"))
        html = (
            '<span style="color:{muted};">{ts}  </span>'
            '<span style="color:{color};">{msg}</span><br>'
        ).format(muted=C_MUTED, ts=ts, color=color, msg=safe)
        self.log_text.moveCursor(QTextCursor.End)
        self.log_text.insertHtml(html)
        self.log_text.moveCursor(QTextCursor.End)

    def _update_status(self, who, state):
        labels = {
            "stopped":      ("● Arrêté",       "status_off"),
            "listening":    ("● En écoute…",   "status_warn"),
            "connecting":   ("● Connexion…",   "status_warn"),
            "connected":    ("● Connecté ✓",   "status_ok"),
            "disconnected": ("● Déconnecté",   "status_err"),
            "error":        ("● Erreur",        "status_err"),
        }
        text, obj = labels.get(state, ("● ?", "status_off"))
        lbl = self.lbl_srv if who == "server" else self.lbl_cli
        lbl.setText(text)
        lbl.setObjectName(obj)
        lbl.setStyleSheet("")
        self.setStyleSheet(STYLESHEET)

    def _set_transfer(self, active):
        if active:
            self.lbl_transfer.setText("✅ ACTIF — envoi vers le serveur")
            self.lbl_transfer.setObjectName("status_ok")
        else:
            self.lbl_transfer.setText("⏸  PAUSÉ — frappe locale")
            self.lbl_transfer.setObjectName("status_warn")
        self.lbl_transfer.setStyleSheet("")
        self.setStyleSheet(STYLESHEET)

    def closeEvent(self, event):
        self._stop()
        event.accept()


HELP_TEXT = """
╔══════════════════════════════════════════════════════════╗
║          KVMSoft v1.2 — Guide d'utilisation              ║
╚══════════════════════════════════════════════════════════╝

MODES
─────
  🖥  Serveur        Reçoit les frappes réseau → les injecte dans X11.
                     Adresse d'écoute : 0.0.0.0 (toutes interfaces)
                     Lancer avec : DISPLAY=:0 kvmsoft

  💻  Client         Capture le clavier local → l'envoie au serveur.
                     Nécessite sudo ou groupe 'input'.

TOUCHE DE BASCULE
─────────────────
  Défaut : KEY_F12   
  Tapez sur F12 pour desactiver l'application rapidement , et dans ce cas vous pouvez utiliser le clavier sur l'ordinateur original du clavier.
  Re-tapez F12 pour re-activer l'application rapidement .


PRÉREQUIS
─────────
  pip3 install PyQt5 evdev python-xlib
  — ou —
  sudo apt install python3-pyqt5 python3-evdev python3-xlib

RÉSEAU
──────
  sudo ufw allow 55555/tcp

COMPATIBILITÉ
─────────────
  Python 3.6+  ·  Ubuntu 18.04 / 20.04 / 22.04 / 24.04  ·  Linux
"""



def main():
    if not PYQT5_OK:
        print("[ERREUR] PyQt5 non installé.")
        print("  sudo apt install python3-pyqt5")
        print("  — ou —  pip3 install PyQt5")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Sauvegarder l'icône PNG dans le dossier utilisateur.

    icon_path = os.path.expanduser("~/.local/share/icons/kvmsoft.png")
    _save_icon_file(icon_path, 128)

    icon = _make_icon()
    app.setWindowIcon(icon)

    win = KVMSoftWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()