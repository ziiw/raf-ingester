from PyQt6.QtGui import QIcon, QPainter, QColor, QPixmap, QPainterPath
from PyQt6.QtCore import Qt, QSize, QRect

def create_app_icon():
    # Create base pixmap
    size = 512  # Large size for better scaling
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    # Create painter
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Define colors
    bg_color = QColor("#2d2d2d")
    text_color = QColor("#ffd700")  # Gold color
    
    # Create circular background
    painter.setBrush(bg_color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size, size)
    
    # Add RAF text
    font = painter.font()
    font.setPixelSize(size // 3)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(text_color)
    
    text_rect = QRect(0, 0, size, size)
    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "RAF")
    
    painter.end()
    
    return QIcon(pixmap) 