from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class MiniChart(QWidget):
    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.values: list[float] = []
        self.color = color
        self.setMinimumHeight(90)

    def set_values(self, values: list[float]) -> None:
        self.values = values[-30:]
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(8, 8, max(1, self.width() - 16), max(1, self.height() - 16))
        painter.setPen(QPen(QColor("#354064"), 1))
        painter.drawRect(area)
        if not self.values:
            painter.setPen(QColor("#7f89ad"))
            painter.drawText(area, "No data yet")
            return
        if len(self.values) == 1:
            painter.setPen(QPen(QColor(self.color), 2))
            point = QPointF(area.center().x(), area.center().y())
            painter.drawEllipse(point, 3, 3)
            painter.drawText(point.x() + 8, point.y() + 4, f"{self.values[0]:g}")
            return
        low, high = min(self.values), max(self.values)
        span = max(1.0, high - low)
        points = [
            QPointF(
                area.left() + i * area.width() / (len(self.values) - 1),
                area.bottom() - (v - low) / span * area.height(),
            )
            for i, v in enumerate(self.values)
        ]
        painter.setPen(QPen(QColor(self.color), 2))
        for first, second in zip(points, points[1:], strict=False):
            painter.drawLine(first, second)
        painter.setBrush(QColor(self.color))
        painter.drawEllipse(points[-1], 3, 3)
        painter.drawText(points[-1].x() - 42, points[-1].y() - 8, f"{self.values[-1]:g}")
