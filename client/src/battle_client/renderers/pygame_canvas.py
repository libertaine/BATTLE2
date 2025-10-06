from PySide6 import QtCore, QtWidgets
import os, pygame

class PygameCanvas(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow)
        self._started = False
        self._timer = None
        self.renderer = None

    def showEvent(self, e):
        super().showEvent(e)
        if not self._started:
            os.environ["SDL_WINDOWID"] = str(int(self.winId()))
            os.environ["SDL_VIDEODRIVER"] = "windib" if os.name == "nt" else "x11"
            pygame.display.init()
            from battle_client.renderers.pygame_renderer import PygameRenderer
            self.renderer = PygameRenderer()
            self._timer = QtCore.QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(16)  # ~60 FPS
            self._started = True

    def _tick(self):
        if not self.renderer:
            return
        try:
            self.renderer.update()
            pygame.display.flip()
        except Exception as e:
            print("[tick error]", e)
