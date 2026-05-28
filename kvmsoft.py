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
DEFAULT_DEV  = "/dev/input/event3"             
EVDEV_OFFSET = 8
CONFIG_PATH  = os.path.expanduser("~/.config/kvmsoft.json")   

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




def get_local_ips():
    """Retourne les adresses IPv4 locales (hors loopback) via les interfaces reseau."""
    import subprocess, re as _re
    ips = []
    # Methode principale : commande 'ip -4 addr show'
    try:
        out = subprocess.check_output(
            ["ip", "-4", "addr", "show"],
            stderr=subprocess.DEVNULL, timeout=3
        ).decode()
        for m in _re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)", out):
            addr = m.group(1)
            if not addr.startswith("127."):
                ips.append(addr)
    except Exception:
        pass
    # Fallback : socket UDP factice
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            addr = s.getsockname()[0]
            s.close()
            if not addr.startswith("127."):
                ips.append(addr)
        except Exception:
            pass
    return ips if ips else ["Aucune interface reseau active"]

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



KEYBOARD_PHOTO_B64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAkGBwgHBgkIBwgKCgkLDRYPDQwMDRsUFRAWIB0iIiAdHx8kKDQsJCYxJx8fLT0tMTU3"
    "Ojo6Iys/RD84QzQ5Ojf/2wBDAQoKCg0MDRoPDxo3JR8lNzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3"
    "Nzc3Nzc3Nzf/wAARCAG8A4QDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
    "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
    "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
    "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
    "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
    "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
    "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDxA8Ug+Y0rcmheDzSJ6D1j4pp+8RV22jEkee4NUn4lb61Kd2TF3YKM8d6lRSDShQy5HWp7"
    "Yhjtbg0mxORVuIyjBscGnw7ZBtetRrPzrd0x8w5WscAoxB4IpRlzISlzIJIvKkwenY0uAR1q0pS4j2ScN2NVGQxOUkGCKuOo07hy"
    "p45qeKQNx19qrlzn5eKVAQc96vlTBq61NCOAOMocH0qfyg8flXCnb2butUYJXjbOcj0NbFnqVo5EdwNp9TUypyWpjLmWxhXlrLav"
    "h+UP3XHQ1ABXavYRzwkRgSwt1GenuK5nUtNlsm3YLRHo2OnsacZX3NKdVS0e5RpaSlqzYWikpaBC0UlFMBaKKKBBS0lLTAKKKKAF"
    "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"
    "4fy/n/mO8f5F+P8AmWv7LiJx9uX/AL8t/jTv7KhH/L+v/flv8ap4pCPYUuaP8v5/5g5xX2F+P+Zd/suAf8xBP+/Df40f2ZB/z/p/"
    "35aqOB6UUuaP8v5/5gqkf5F+P+Zd/s2D/n/X/vy3+NO/sy3/AOggv/fhv8ao49qXb7Uc8f5V+P8AmWpx/kX4/wCZc/s23/6CC/8A"
    "fhv8aBp1v/0EF/78NVPHtQRS51/L+f8AmVzxX2F+P+Ze/s6176gn/fhqQafbf8/6/wDfhqo4pQPajnX8q/H/ADGqsf8An2vx/wAy"
    "/wD2dbH/AJiCD/ti1O/s20A51OP/AL8PWfigilzrt+f+ZXtY/wDPtfj/AJl7+zrT/oJJ/wB+Hp39nWf/AEE0/wC/DVm0oFLmXb8/"
    "8w9vH/n2vx/zNH+zbMc/2mn/AH4akGn2hPOoqB/1waqGKNtHMu35/wCZft4/8+1+P+Zo/wBmWWP+Qon/AIDvTTptmOmppn/rg1Zx"
    "pKm5LxEf+fa/H/Mv/wBnWpHGpJ/35aj+zbb/AKCKf9+WqjilxSF7eP8Az7X/AJN/mXP7Nth/zEE/78tSHTrYDjUE/wC/LVTIpKBP"
    "ERX/AC7X/k3/AMkW/sFv/wA/6f8AfpqQafAf+X9P+/TVVoxRbzJ+sx/59r/yb/5IuLplueuoxj/tk1L/AGbaZ51OP/vy9U8UYqHF"
    "v7T/AA/yH7eP/Ptf+Tf5l7+zLP8A6Csf/fh6Bpdp/wBBWL/vy9UKMUuR/wAz/D/IX1iP/Ptf+Tf5l/8Asyz/AOgpH/34aj+zrP8A"
    "6Ckf/fh6pAUYo5H/ADP8P8ivrEf+fa/8m/zLv9nWf/QUj/78NS/2bZ4/5Csf/flqz8UYo9m/5n+H+QfWY/8APtf+Tf5l/wDs60/6"
    "Ccf/AH5amnT7XP8AyEUP/bFqphaCKfI/5n+H+Q/rS/59r/yb/MtfYbf/AJ/k/wC/TUhs4M/8fqf9+2qqabVcnmH1xf8APtf+Tf8A"
    "yRc+xwf8/qf9+2pfslv/AM/qf9+2qlSUcnmH11f8+4/+Tf8AyRe+yQf8/qf9+2o+ywf8/qf9+zVGkpcnmUscv+fa/wDJv/kjQ+zW"
    "/wDz+p/3waUW1v3vY/8AvhqzqKPZor+0P+na/wDJv8zS+z2w63yf9+2o8m1H/L6n4RtWaaSjkQ1mP/Ttf+Tf5mp5dqf+X1P+/bUn"
    "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"
)

class FooterWidget(QWidget):
    """Zone de pied de page : photo de clavier avec fondu, bouton Demarrer superpose."""

    btn_clicked = None  

    def __init__(self, parent=None):
        super(FooterWidget, self).__init__(parent)
        self.setFixedHeight(130)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAutoFillBackground(False)

        self._kbd_pixmap = None
        if PYQT5_OK:
            try:
                from PyQt5.QtGui import QPixmap
                raw = base64.b64decode(KEYBOARD_PHOTO_B64)
                px = QPixmap()
                px.loadFromData(raw, "JPEG")
                self._kbd_pixmap = px
            except Exception as e:
                print("[KVMSoft] Erreur chargement photo clavier:", e)

        # Bouton demarrer/arreter centre par-dessus
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setAlignment(Qt.AlignCenter)

        self.btn_start = QPushButton("\u25b6  Demarrer")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setFixedWidth(200)
        lay.addWidget(self.btn_start, 0, Qt.AlignCenter)

    def paintEvent(self, event):
        from PyQt5.QtGui import (QPainter, QLinearGradient, QColor,
                                  QBrush, QImage)
        from PyQt5.QtCore import Qt as Qt_

        W, H = self.width(), self.height()
        if W <= 0 or H <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        if self._kbd_pixmap and not self._kbd_pixmap.isNull():
            # Dessiner la photo en couvrant tout le widget
            scaled = self._kbd_pixmap.scaled(
                W, H, Qt_.KeepAspectRatioByExpanding, Qt_.SmoothTransformation
            )
            # Centrer si plus large
            ox = (scaled.width() - W) // 2
            oy = (scaled.height() - H) // 2
            p.drawPixmap(0, 0, scaled, ox, oy, W, H)
        else:
            p.fillRect(0, 0, W, H, QColor("#13132a"))

        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.00, QColor(30, 30, 46, 210))   
        grad.setColorAt(0.40, QColor(30, 30, 46, 130))   
        grad.setColorAt(0.70, QColor(30, 30, 46,  60))    
        grad.setColorAt(1.00, QColor(30, 30, 46, 180))   
        p.fillRect(0, 0, W, H, grad)

        p.end()



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

        self.footer = FooterWidget()
        self.footer.btn_start.clicked.connect(self._toggle_service)
        root.addWidget(body, 1)
        root.addWidget(self.footer)
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

        # --- Boite info serveur : IPs locales ---
        self.server_info_box = QGroupBox("\U0001f5a5  Serveur — Adresse de connexion")
        srv_lay = QVBoxLayout(self.server_info_box)
        hint = QLabel("L'autre ordinateur (client) doit saisir :")
        hint.setStyleSheet("color: {};".format(C_MUTED))
        srv_lay.addWidget(hint)
        local_ips = get_local_ips()
        for ip in local_ips:
            r = QHBoxLayout()
            ic = QLabel("\U0001f4e1")
            ic.setFixedWidth(22)
            r.addWidget(ic)
            lbl_ip = QLabel("<b>{}</b>".format(ip))
            lbl_ip.setStyleSheet(
                "color: {}; font-size: 13pt; font-family: monospace;".format(C_GREEN)
            )
            lbl_ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
            r.addWidget(lbl_ip)
            ph = QLabel("  port {}".format(self.cfg.get("port", str(DEFAULT_PORT))))
            ph.setStyleSheet("color: {};".format(C_MUTED))
            r.addWidget(ph)
            r.addStretch()
            srv_lay.addLayout(r)
        note = QLabel("\u26a0  sudo ufw allow {}/tcp".format(self.cfg.get("port", str(DEFAULT_PORT))))
        note.setStyleSheet("color: {}; font-size: 8pt;".format(C_YELLOW))
        srv_lay.addWidget(note)
        self.server_info_box.setVisible(False)
        lay.addWidget(self.server_info_box)

        self.client_box = QGroupBox("\u2328  Client \u2014 Clavier local")
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
        is_server = self.radio_server.isChecked()
        self.client_box.setVisible(not is_server)
        self.server_info_box.setVisible(is_server)

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
        self.footer.btn_start.setText("\u23f9  Arreter")
        self.footer.btn_start.setObjectName("btn_stop")
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
        self.footer.btn_start.setText("\u25b6  Demarrer")
        self.footer.btn_start.setObjectName("btn_start")
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


    icon_path = os.path.expanduser("~/.local/share/icons/kvmsoft.png")
    _save_icon_file(icon_path, 128)

    icon = _make_icon()
    app.setWindowIcon(icon)

    win = KVMSoftWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()