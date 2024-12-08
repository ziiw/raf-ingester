import sys
import os
from pathlib import Path
import rawpy
from PIL import Image
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
import weakref
import io
import time

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                           QHBoxLayout, QLabel, QPushButton, QFileDialog,
                           QScrollArea, QComboBox, QGridLayout, QProgressBar,
                           QStackedWidget, QSizePolicy)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QPixmap, QImage, QKeyEvent, QTransform

from app_icon import create_app_icon

class ThumbnailLoader(QObject):
    thumbnail_ready = pyqtSignal(int, QPixmap, str, int)
    batch_complete = pyqtSignal()
    progress_updated = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._queue = Queue()
        self._cache = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        
    def stop(self):
        self._stop_event.set()
        
    def clear_cache(self):
        self._cache.clear()
        
    def load_thumbnails(self, files):
        self._stop_event.clear()
        self._queue = Queue()
        
        for i, file in enumerate(files):
            self._queue.put((i, str(file)))
        
        thread = threading.Thread(target=self._process_queue)
        thread.daemon = True
        thread.start()
        
    def _process_queue(self):
        total_files = self._queue.qsize()
        processed = 0
        
        while not self._queue.empty() and not self._stop_event.is_set():
            idx, file_path = self._queue.get()
            
            # Check cache first
            if file_path in self._cache:
                pixmap, orientation = self._cache[file_path]
                self.thumbnail_ready.emit(idx, pixmap, file_path, orientation)
                processed += 1
                self.progress_updated.emit(int(processed * 100 / total_files))
                continue
            
            # Submit to thread pool for RAF processing
            future = self._executor.submit(self._load_thumbnail, idx, file_path)
            future.add_done_callback(self._handle_thumbnail_result)
            
            processed += 1
            self.progress_updated.emit(int(processed * 100 / total_files))
            
        self.batch_complete.emit()
    
    def _load_thumbnail(self, idx, file_path):
        try:
            with rawpy.imread(file_path) as raw:
                # Try to get the embedded JPEG preview first
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        image_data = thumb.data
                        qimage = QImage.fromData(image_data)
                        
                        # Get orientation from metadata
                        orientation = 0
                        try:
                            if hasattr(raw, 'metadata') and hasattr(raw.metadata, 'orientation'):
                                orientation = raw.metadata.orientation
                            else:
                                # Fallback to checking raw sizes
                                raw_height = raw.sizes.raw_height
                                raw_width = raw.sizes.raw_width
                                if raw_height > raw_width:  # Portrait image
                                    orientation = 90
                        except:
                            # If metadata fails, check image dimensions
                            if qimage.height() > qimage.width():  # Portrait image
                                orientation = 90
                        
                        # Apply rotation based on orientation
                        if orientation == 90 or orientation == 5:
                            transform = QTransform()
                            qimage = qimage.transformed(transform.rotate(90))
                        elif orientation == 270 or orientation == 7:
                            transform = QTransform()
                            qimage = qimage.transformed(transform.rotate(270))
                        elif orientation == 180 or orientation == 3:
                            transform = QTransform()
                            qimage = qimage.transformed(transform.rotate(180))
                        
                        return idx, qimage, file_path, orientation
                except Exception as e:
                    print(f"Error extracting thumbnail: {str(e)}")
                    pass
                
                return idx, None, file_path, 0
                
        except Exception as e:
            print(f"Error loading RAF file: {str(e)}")
            
        return idx, None, file_path, 0
    
    def _handle_thumbnail_result(self, future):
        try:
            idx, qimage, file_path, orientation = future.result()
            if qimage:
                pixmap = QPixmap.fromImage(qimage)
                self._cache[file_path] = (pixmap, orientation)
                self.thumbnail_ready.emit(idx, pixmap, file_path, orientation)
        except Exception as e:
            print(f"Error handling thumbnail result: {str(e)}")

class ThumbnailWidget(QWidget):
    clicked = pyqtSignal(int)
    score_changed = pyqtSignal(int, int)  # (index, new_score)
    
    def __init__(self, index):
        super().__init__()
        self.index = index
        self.score = 0
        self.score_buttons = []  # Store references to score buttons
        self.initUI()
        
    def initUI(self):
        # Make widget expand to fill available space
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(300, 350)
        
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Image container with dark background
        image_container = QWidget()
        image_container.setStyleSheet("background-color: #2d2d2d; border-radius: 5px;")
        image_container_layout = QVBoxLayout(image_container)
        image_container_layout.setContentsMargins(10, 10, 10, 10)
        
        # Image label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(280, 280)
        self.image_label.setStyleSheet("background-color: transparent;")
        image_container_layout.addWidget(self.image_label)
        
        layout.addWidget(image_container)
        
        # Info layout with dark background
        info_container = QWidget()
        info_container.setStyleSheet("""
            QWidget {
                background-color: #2d2d2d;
                border-radius: 5px;
                color: white;
            }
        """)
        info_layout = QVBoxLayout(info_container)
        info_layout.setSpacing(4)
        info_layout.setContentsMargins(10, 8, 10, 8)
        
        # Filename label
        self.filename_label = QLabel()
        self.filename_label.setStyleSheet("font-weight: bold; color: white;")
        info_layout.addWidget(self.filename_label)
        
        # DateTime label
        self.datetime_label = QLabel()
        self.datetime_label.setStyleSheet("color: #b0b0b0;")
        info_layout.addWidget(self.datetime_label)
        
        # Score display
        self.score_display = QLabel("Score: 0★")
        self.score_display.setStyleSheet("""
            color: #ffd700;
            font-weight: bold;
            font-size: 14px;
            padding: 2px;
        """)
        info_layout.addWidget(self.score_display)
        
        # Score buttons layout
        score_layout = QHBoxLayout()
        score_layout.setSpacing(4)
        
        # Add star buttons
        for i in range(6):
            btn = QPushButton(f"{i}★")
            btn.setMaximumWidth(35)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton { 
                    padding: 4px;
                    background-color: #3d3d3d;
                    color: #b0b0b0;
                    border: none;
                    border-radius: 3px;
                    font-size: 13px;
                }
                QPushButton:hover { 
                    background-color: #4d4d4d;
                    color: #ffd700;
                }
                QPushButton:checked {
                    background-color: #ffd700;
                    color: black;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, score=i: self.set_score(score))
            score_layout.addWidget(btn)
            self.score_buttons.append(btn)
        
        info_layout.addLayout(score_layout)
        layout.addWidget(info_container)
    
    def set_score(self, score):
        self.score = score
        self.score_changed.emit(self.index, score)
        self.update_score_display()
        
        # Update button states
        for i, btn in enumerate(self.score_buttons):
            btn.setChecked(i == score)
    
    def update_score_display(self):
        # Update score label
        self.score_display.setText(f"Score: {self.score}★")
        
        # Update score indicator on image
        if hasattr(self, 'score_label'):
            self.score_label.deleteLater()
            
        if self.score > 0:
            self.score_label = QLabel(f"{self.score}★", self.image_label)
            self.score_label.setStyleSheet("""
                background-color: #ffd700;
                color: black;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            """)
            self.score_label.move(8, 8)
    
    def setPixmap(self, pixmap):
        if pixmap:
            scaled_pixmap = pixmap.scaled(QSize(280, 280), 
                                        Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
    
    def set_info(self, filename, datetime_str):
        self.filename_label.setText(filename)
        self.datetime_label.setText(datetime_str)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)

class GridWidget(QWidget):
    thumbnail_clicked = pyqtSignal(int)
    thumbnail_scored = pyqtSignal(int, int)
    
    def __init__(self):
        super().__init__()
        # Create a container widget for the grid
        self.container = QWidget()
        self.container.setStyleSheet("background-color: #1a1a1a;")
        
        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.container)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1a1a1a;
            }
            QScrollBar:vertical {
                background-color: #2d2d2d;
                width: 12px;
            }
            QScrollBar::handle:vertical {
                background-color: #4d4d4d;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #5d5d5d;
            }
        """)
        
        # Main layout for this widget
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Grid layout for the thumbnails
        self.layout = QGridLayout(self.container)
        self.layout.setSpacing(15)
        self.layout.setContentsMargins(15, 15, 15, 15)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.thumbnails = {}
        self.placeholder_pixmap = QPixmap(280, 280)
        self.placeholder_pixmap.fill(Qt.GlobalColor.black)
    
    def clear(self):
        for thumb in self.thumbnails.values():
            self.layout.removeWidget(thumb)
            thumb.deleteLater()
        self.thumbnails.clear()
    
    def prepare_thumbnails(self, count):
        self.clear()
        columns = max(2, self.width() // 340)  # Dynamically calculate number of columns
        
        for i in range(count):
            row = i // columns
            col = i % columns
            
            thumb = ThumbnailWidget(i)
            thumb.setPixmap(self.placeholder_pixmap)
            thumb.clicked.connect(self.thumbnail_clicked.emit)
            thumb.score_changed.connect(self.thumbnail_scored.emit)
            self.layout.addWidget(thumb, row, col)
            self.thumbnails[i] = thumb
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.thumbnails:
            # Recalculate grid layout when window is resized
            items = [(index, thumb) for index, thumb in self.thumbnails.items()]
            columns = max(2, self.width() // 340)
            
            for index, thumb in items:
                self.layout.removeWidget(thumb)
                row = index // columns
                col = index % columns
                self.layout.addWidget(thumb, row, col)
    
    def update_thumbnail(self, index, pixmap, score=0, orientation=0, filename="", datetime_str=""):
        if index in self.thumbnails:
            thumb = self.thumbnails[index]
            
            # Apply rotation based on orientation
            if orientation == 90:
                transform = QTransform()
                pixmap = pixmap.transformed(transform.rotate(90))
            elif orientation == 270:
                transform = QTransform()
                pixmap = pixmap.transformed(transform.rotate(270))
            elif orientation == 180:
                transform = QTransform()
                pixmap = pixmap.transformed(transform.rotate(180))
            
            thumb.setPixmap(pixmap)
            thumb.set_info(filename, datetime_str)
            if score > 0:
                thumb.set_score(score)

class SingleImageWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)
        self.current_orientation = 0
    
    def set_image(self, pixmap, orientation=0):
        if pixmap:
            self.current_orientation = orientation
            # Apply rotation based on orientation
            if orientation == 90:
                transform = QTransform()
                pixmap = pixmap.transformed(transform.rotate(90))
            elif orientation == 270:
                transform = QTransform()
                pixmap = pixmap.transformed(transform.rotate(270))
            elif orientation == 180:
                transform = QTransform()
                pixmap = pixmap.transformed(transform.rotate(180))
            
            scaled_pixmap = pixmap.scaled(self.size(), 
                                        Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation)
            self.image_label.setPixmap(scaled_pixmap)
        else:
            self.image_label.clear()
            self.current_orientation = 0
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.image_label.pixmap():
            self.set_image(self.image_label.pixmap().copy(), self.current_orientation)

class RAFImporter(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAF Photo Importer")
        self.setMinimumSize(1200, 800)
        
        # Initialize variables
        self.current_folder = None
        self.raf_files = []
        self.current_index = 0
        self.scores = {}
        self.is_grid_view = True
        
        # Initialize thumbnail loader
        self.thumbnail_loader = ThumbnailLoader()
        self.thumbnail_loader.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.thumbnail_loader.progress_updated.connect(self._update_progress)
        self.thumbnail_loader.batch_complete.connect(self._on_loading_complete)
        
        self.init_ui()
    
    def init_ui(self):
        # Create central widget and main layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # Create top toolbar
        toolbar = QHBoxLayout()
        
        # Add folder selection button
        self.folder_btn = QPushButton("Select Folder")
        self.folder_btn.clicked.connect(self.select_folder)
        toolbar.addWidget(self.folder_btn)
        
        # Add score filter dropdown
        self.score_filter = QComboBox()
        self.score_filter.addItems(["All", "0★", "1★", "2★", "3★", "4★", "5★"])
        self.score_filter.currentTextChanged.connect(self.filter_images)
        toolbar.addWidget(self.score_filter)
        
        # Add view toggle button
        self.view_toggle_btn = QPushButton("Toggle View (Space)")
        self.view_toggle_btn.clicked.connect(self.toggle_view)
        toolbar.addWidget(self.view_toggle_btn)
        
        # Add export button
        self.export_btn = QPushButton("Export Selected")
        self.export_btn.clicked.connect(self.export_selected)
        toolbar.addWidget(self.export_btn)
        
        self.main_layout.addLayout(toolbar)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.main_layout.addWidget(self.progress_bar)
        
        # Create stacked widget for views
        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)
        
        # Create grid view
        self.grid_widget = GridWidget()
        self.grid_widget.thumbnail_clicked.connect(self.on_thumbnail_clicked)
        self.grid_widget.thumbnail_scored.connect(self.on_thumbnail_scored)
        
        # Create single image view
        self.single_image_widget = SingleImageWidget()
        
        # Add both widgets to the stacked widget
        self.stacked_widget.addWidget(self.grid_widget)
        self.stacked_widget.addWidget(self.single_image_widget)
        
        # Create bottom toolbar with navigation and scoring
        bottom_toolbar = QHBoxLayout()
        
        # Navigation buttons
        self.prev_btn = QPushButton("Previous (←)")
        self.prev_btn.clicked.connect(self.show_previous)
        bottom_toolbar.addWidget(self.prev_btn)
        
        # Star rating buttons
        for i in range(6):
            star_btn = QPushButton(f"{i}★")
            star_btn.clicked.connect(lambda checked, score=i: self.set_score(score))
            bottom_toolbar.addWidget(star_btn)
        
        self.next_btn = QPushButton("Next (→)")
        self.next_btn.clicked.connect(self.show_next)
        bottom_toolbar.addWidget(self.next_btn)
        
        self.main_layout.addLayout(bottom_toolbar)
        
        # Add status bar for file info
        self.statusBar().showMessage("No folder selected")
        
        # Enable focus for keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    
    def _on_thumbnail_ready(self, index, pixmap, file_path, orientation):
        try:
            # Get file info
            file_path = Path(file_path)
            filename = file_path.name
            
            # Get creation date from RAF file
            with rawpy.imread(str(file_path)) as raw:
                try:
                    # Try to get the date from metadata
                    timestamp = os.path.getmtime(file_path)
                    datetime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                except:
                    datetime_str = "Date unknown"
            
            score = self.scores.get(str(file_path), 0)
            self.grid_widget.update_thumbnail(index, pixmap, score, orientation, filename, datetime_str)
        except Exception as e:
            print(f"Error updating thumbnail: {str(e)}")
    
    def _update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def _on_loading_complete(self):
        self.progress_bar.setVisible(False)
        self.folder_btn.setEnabled(True)
    
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_view()
        elif event.key() == Qt.Key.Key_Left:
            self.show_previous()
        elif event.key() == Qt.Key.Key_Right:
            self.show_next()
        elif event.key() >= Qt.Key.Key_0 and event.key() <= Qt.Key.Key_5:
            self.set_score(int(event.text()))
        else:
            super().keyPressEvent(event)
    
    def toggle_view(self):
        if not self.raf_files:
            return
            
        self.is_grid_view = not self.is_grid_view
        if self.is_grid_view:
            self.stacked_widget.setCurrentWidget(self.grid_widget)
        else:
            self.stacked_widget.setCurrentWidget(self.single_image_widget)
            self.show_current_image()
    
    def on_thumbnail_clicked(self, index):
        self.current_index = index
        self.is_grid_view = False
        self.stacked_widget.setCurrentWidget(self.single_image_widget)
        self.show_current_image()
    
    def load_grid_view(self):
        if not self.raf_files:
            return
            
        self.grid_widget.prepare_thumbnails(len(self.raf_files))
        self.thumbnail_loader.load_thumbnails(self.raf_files)
    
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.current_folder = Path(folder)
            self.raf_files = sorted([f for f in self.current_folder.glob("*.RAF")])
            
            if self.raf_files:
                self.current_index = 0
                self.folder_btn.setEnabled(False)
                self.progress_bar.setVisible(True)
                self.progress_bar.setValue(0)
                
                if self.is_grid_view:
                    self.load_grid_view()
                else:
                    self.show_current_image()
                    self.folder_btn.setEnabled(True)
            else:
                self.statusBar().showMessage("No RAF files found in selected folder")
    
    def show_current_image(self):
        if not self.raf_files:
            return
        
        current_file = self.raf_files[self.current_index]
        try:
            with rawpy.imread(str(current_file)) as raw:
                # Get orientation from metadata or image dimensions
                orientation = 0
                try:
                    if hasattr(raw, 'metadata') and hasattr(raw.metadata, 'orientation'):
                        orientation = raw.metadata.orientation
                    else:
                        # Fallback to checking raw sizes
                        raw_height = raw.sizes.raw_height
                        raw_width = raw.sizes.raw_width
                        if raw_height > raw_width:  # Portrait image
                            orientation = 90
                except:
                    pass
                
                thumb = raw.extract_thumb()
                if thumb.format == rawpy.ThumbFormat.JPEG:
                    image_data = thumb.data
                    qimage = QImage.fromData(image_data)
                    
                    # If no orientation from metadata, check image dimensions
                    if orientation == 0 and qimage.height() > qimage.width():
                        orientation = 90
                    
                    # Apply rotation based on orientation
                    if orientation == 90 or orientation == 5:
                        transform = QTransform()
                        qimage = qimage.transformed(transform.rotate(90))
                    elif orientation == 270 or orientation == 7:
                        transform = QTransform()
                        qimage = qimage.transformed(transform.rotate(270))
                    elif orientation == 180 or orientation == 3:
                        transform = QTransform()
                        qimage = qimage.transformed(transform.rotate(180))
                    
                    pixmap = QPixmap.fromImage(qimage)
                    self.single_image_widget.set_image(pixmap)
                    
            score = self.scores.get(str(current_file), 0)
            self.statusBar().showMessage(f"{current_file.name} - Score: {score}★")
        except Exception as e:
            self.statusBar().showMessage(f"Error loading image: {str(e)}")
    
    def show_next(self):
        if self.raf_files and self.current_index < len(self.raf_files) - 1:
            self.current_index += 1
            if not self.is_grid_view:
                self.show_current_image()
    
    def show_previous(self):
        if self.raf_files and self.current_index > 0:
            self.current_index -= 1
            if not self.is_grid_view:
                self.show_current_image()
    
    def set_score(self, score):
        if not self.raf_files:
            return
        current_file = str(self.raf_files[self.current_index])
        print(f"Setting score {score} for {current_file}")  # Debug info
        self.scores[current_file] = score
        self.statusBar().showMessage(f"{Path(current_file).name} - Score: {score}★")
        
        # Always update the grid view thumbnail, regardless of current view mode
        try:
            cached_data = self.thumbnail_loader._cache.get(current_file)
            if cached_data:
                pixmap, orientation = cached_data
                filename = Path(current_file).name
                # Get the timestamp
                timestamp = os.path.getmtime(current_file)
                datetime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                # Update the thumbnail in grid view
                self.grid_widget.update_thumbnail(
                    self.current_index,
                    pixmap,
                    score,
                    orientation,
                    filename,
                    datetime_str
                )
        except Exception as e:
            print(f"Error updating thumbnail score: {str(e)}")
    
    def filter_images(self, filter_text):
        if not self.current_folder:
            return
            
        if filter_text == "All":
            self.raf_files = sorted([f for f in self.current_folder.glob("*.RAF")])
        else:
            score = int(filter_text[0])
            self.raf_files = sorted([
                Path(f) for f, s in self.scores.items()
                if s == score and Path(f).suffix.upper() == ".RAF"
            ])
        
        if self.raf_files:
            self.current_index = 0
            if self.is_grid_view:
                self.load_grid_view()
            else:
                self.show_current_image()
        else:
            if self.is_grid_view:
                self.grid_widget.clear()
            else:
                self.single_image_widget.set_image(None)
            self.statusBar().showMessage("No images match the selected filter")
    
    def export_selected(self):
        if not self.current_folder:
            return
            
        # First, count how many files we'll export
        files_to_export = []
        for file_path, score in self.scores.items():
            if score > 0:
                if isinstance(file_path, str):
                    file_path = Path(file_path)
                if file_path.exists():
                    files_to_export.append((file_path, score))
                else:
                    print(f"File not found: {file_path}")
        
        if not files_to_export:
            self.statusBar().showMessage("No scored images found to export")
            return
            
        # Ask for export directory
        export_folder = QFileDialog.getExistingDirectory(self, 
            "Select Export Folder", 
            str(Path.home()),
            QFileDialog.Option.ShowDirsOnly)
            
        if not export_folder:
            return
            
        export_path = Path(export_folder)
        exported = 0
        
        # Show progress dialog
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage(f"Exporting {len(files_to_export)} images...")
        QApplication.processEvents()  # Ensure UI updates
        
        # Export files
        for i, (raf_file, score) in enumerate(files_to_export):
            try:
                self.statusBar().showMessage(f"Processing {raf_file.name}...")
                QApplication.processEvents()  # Ensure UI updates
                
                with rawpy.imread(str(raf_file)) as raw:
                    # Get orientation from metadata or image dimensions
                    orientation = 0
                    try:
                        if hasattr(raw, 'metadata') and hasattr(raw.metadata, 'orientation'):
                            orientation = raw.metadata.orientation
                        else:
                            # Fallback to checking raw sizes
                            raw_height = raw.sizes.raw_height
                            raw_width = raw.sizes.raw_width
                            if raw_height > raw_width:  # Portrait image
                                orientation = 90
                    except:
                        pass
                    
                    # Process RAW with optimal settings for Fujifilm
                    rgb = raw.postprocess(
                        use_camera_wb=True,    # Use camera white balance
                        use_auto_wb=False,     # Don't use auto white balance
                        bright=1.2,            # Slightly increase brightness
                        no_auto_bright=True,   # Disable auto brightness to keep exposure control
                        output_bps=8,          # Use 8-bit output for JPEG compatibility
                        gamma=(2.222, 4.5),    # Standard gamma curve for Fujifilm
                        user_flip=0,           # We'll handle rotation separately
                        demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,  # High quality demosaicing
                        output_color=rawpy.ColorSpace.sRGB,  # Use sRGB color space
                        highlight_mode=rawpy.HighlightMode.Blend,  # Better highlight handling
                        fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Full  # Better noise reduction
                    )
                    
                    # Convert to PIL Image
                    image = Image.fromarray(rgb)
                    
                    # Apply rotation based on orientation
                    if orientation == 90 or orientation == 5:
                        image = image.transpose(Image.Transpose.ROTATE_90)
                    elif orientation == 270 or orientation == 7:
                        image = image.transpose(Image.Transpose.ROTATE_270)
                    elif orientation == 180 or orientation == 3:
                        image = image.transpose(Image.Transpose.ROTATE_180)
                    
                    # Save as high-quality JPEG
                    output_file = export_path / f"{raf_file.stem}.jpg"
                    self.statusBar().showMessage(f"Saving {output_file.name}...")
                    QApplication.processEvents()  # Ensure UI updates
                    
                    image.save(output_file, "JPEG", quality=95, optimize=True)
                    exported += 1
                    
                    # Update progress
                    progress = int((i + 1) * 100 / len(files_to_export))
                    self.progress_bar.setValue(progress)
                    self.statusBar().showMessage(f"Exported {exported}/{len(files_to_export)} images...")
                    QApplication.processEvents()  # Ensure UI updates
                    
            except Exception as e:
                print(f"Error exporting {raf_file}: {str(e)}")
                self.statusBar().showMessage(f"Error exporting {raf_file.name}: {str(e)}")
                QApplication.processEvents()  # Ensure UI updates
        
        # Hide progress bar and show final status
        self.progress_bar.setVisible(False)
        self.statusBar().showMessage(f"Successfully exported {exported} images to {export_folder}")
        QApplication.processEvents()  # Ensure UI updates
    
    def closeEvent(self, event):
        self.thumbnail_loader.stop()
        super().closeEvent(event)
    
    def on_thumbnail_scored(self, index, score):
        if 0 <= index < len(self.raf_files):
            file_path = str(self.raf_files[index])
            self.scores[file_path] = score
            self.statusBar().showMessage(f"{Path(file_path).name} - Score: {score}★")
            
            # If we're in single view mode and this is the current image,
            # update the current image display
            if not self.is_grid_view and index == self.current_index:
                self.show_current_image()

def main():
    app = QApplication(sys.argv)
    
    # Set application-wide style
    app.setStyle('Fusion')
    
    # Set the app icon
    app.setWindowIcon(create_app_icon())
    
    window = RAFImporter()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 