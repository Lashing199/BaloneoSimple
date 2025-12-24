#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 BALONEO SIMPLE - Sistema Manual de Dimensionamiento de Planos Técnicos
Aplicación simplificada para baloneado manual sin IA
"""

import sys
import fitz
import json
import base64
from datetime import datetime
from pathlib import Path
from fractions import Fraction

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog,
                             QTableWidget, QTableWidgetItem, QLineEdit, QComboBox,
                             QMessageBox, QSplitter, QHeaderView, QGroupBox, 
                             QFormLayout, QGraphicsView, QGraphicsScene, 
                             QGraphicsEllipseItem, QGraphicsTextItem, QGraphicsPixmapItem,
                             QDialog, QListWidget, QListWidgetItem, QDialogButtonBox, QInputDialog)
from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QBrush, QTransform

class BalloonGraphicsView(QGraphicsView):
    """Vista de gráficos personalizada para el baloneo"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        
        # Configurar escena
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        # Variables de estado
        self.balloon_items = []  # Lista de (ellipse, text, data)
        self.pixmap_item = None
        self.dragging_balloon = None
        self.drag_offset = None
        self.panning = False
        self.pan_start_pos = None
        self.zoom_factor = 1.0
        
        # Estilo
        self.setStyleSheet("background-color: #2b2b2b; border: 2px solid #444;")
    
    def load_image(self, pixmap):
        """Cargar imagen en la escena"""
        self.scene.clear()
        self.balloon_items = []
        self.zoom_factor = 1.0
        
        if pixmap:
            self.pixmap_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self.pixmap_item)
            # Expandir la escena para permitir espacio de navegación
            rect = self.pixmap_item.boundingRect()
            margin = max(rect.width(), rect.height()) * 0.6
            self.scene.setSceneRect(
                rect.x() - margin,
                rect.y() - margin,
                rect.width() + margin * 2,
                rect.height() + margin * 2
            )
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
    
    def add_balloon(self, x, y, number, size=35):
        """Agregar globo en la posición especificada"""
        # Crear círculo
        ellipse = QGraphicsEllipseItem(x - size/2, y - size/2, size, size)
        ellipse.setPen(QPen(QColor(0, 120, 215), 2))
        ellipse.setBrush(QBrush(QColor(0, 120, 215, 100)))
        
        # Crear texto
        text = QGraphicsTextItem(str(number))
        text.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont('Arial', int(size * 0.4), QFont.Bold)
        text.setFont(font)
        
        # Hacer que el texto no intercepte eventos del mouse
        text.setFlag(QGraphicsTextItem.ItemIsSelectable, False)
        text.setAcceptHoverEvents(False)
        
        # Centrar texto en el círculo
        text_rect = text.boundingRect()
        text_x = x - text_rect.width() / 2
        text_y = y - text_rect.height() / 2
        text.setPos(text_x, text_y)
        
        # Agregar a la escena
        self.scene.addItem(ellipse)
        self.scene.addItem(text)
        
        # Guardar referencia CON la rotación actual
        balloon_data = {
            'x': x,
            'y': y,
            'number': number,
            'size': size,
            'ellipse': ellipse,
            'text': text,
            'rotation': self.parent_app.current_rotation if hasattr(self.parent_app, 'current_rotation') else 0
        }
        self.balloon_items.append(balloon_data)
        
        return balloon_data
    
    def remove_balloon(self, index):
        """Eliminar globo por índice"""
        if 0 <= index < len(self.balloon_items):
            balloon = self.balloon_items[index]
            self.scene.removeItem(balloon['ellipse'])
            self.scene.removeItem(balloon['text'])
            self.balloon_items.pop(index)
    
    def clear_balloons(self):
        """Limpiar todos los globos"""
        for balloon in self.balloon_items:
            self.scene.removeItem(balloon['ellipse'])
            self.scene.removeItem(balloon['text'])
        self.balloon_items = []
    
    def mousePressEvent(self, event):
        """Manejar clic en la vista"""
        pos_scene = self.mapToScene(event.pos())
        
        # Pan con Shift + clic izquierdo
        if event.button() == Qt.LeftButton and QApplication.keyboardModifiers() == Qt.ShiftModifier:
            self.panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        
        # Ctrl + clic izquierdo: mover globo existente
        if event.button() == Qt.LeftButton and QApplication.keyboardModifiers() == Qt.ControlModifier:
            # Buscar si hay un globo en esta posición
            for balloon in self.balloon_items:
                ellipse = balloon['ellipse']
                if ellipse.contains(pos_scene):
                    self.dragging_balloon = balloon
                    self.drag_offset = QPointF(pos_scene.x() - balloon['x'], pos_scene.y() - balloon['y'])
                    self.setCursor(Qt.ClosedHandCursor)
                    event.accept()
                    return
        
        # Agregar globo con clic izquierdo normal
        if event.button() == Qt.LeftButton and self.pixmap_item:
            # Verificar que está dentro de la imagen
            if self.pixmap_item.contains(pos_scene):
                # Notificar al padre
                if hasattr(self.parent_app, 'on_image_click'):
                    self.parent_app.on_image_click(pos_scene.x(), pos_scene.y())
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Manejar movimiento del mouse"""
        # Arrastrar globo
        if self.dragging_balloon:
            pos_scene = self.mapToScene(event.pos())
            new_x = pos_scene.x() - self.drag_offset.x()
            new_y = pos_scene.y() - self.drag_offset.y()
            
            # Actualizar posición del globo
            balloon = self.dragging_balloon
            size = balloon['size']
            
            # Mover el círculo
            balloon['ellipse'].setRect(new_x - size/2, new_y - size/2, size, size)
            
            # Mover el texto
            text_rect = balloon['text'].boundingRect()
            text_x = new_x - text_rect.width() / 2
            text_y = new_y - text_rect.height() / 2
            balloon['text'].setPos(text_x, text_y)
            
            # Actualizar coordenadas guardadas
            balloon['x'] = new_x
            balloon['y'] = new_y
            
            event.accept()
            return
        
        # Pan con Shift
        if self.panning and self.pan_start_pos:
            # Calcular el desplazamiento en la escena
            new_pos = self.mapToScene(event.pos())
            old_pos = self.mapToScene(self.pan_start_pos)
            delta = new_pos - old_pos
            
            # Actualizar posición de inicio
            self.pan_start_pos = event.pos()
            
            # Mover la vista
            self.horizontalScrollBar().setValue(
                int(self.horizontalScrollBar().value() - delta.x())
            )
            self.verticalScrollBar().setValue(
                int(self.verticalScrollBar().value() - delta.y())
            )
            event.accept()
            return
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Manejar liberación del mouse"""
        if event.button() == Qt.LeftButton:
            if self.dragging_balloon:
                self.dragging_balloon = None
                self.drag_offset = None
                self.setCursor(Qt.ArrowCursor)
                event.accept()
                return
            
            if self.panning:
                self.panning = False
                self.pan_start_pos = None
                self.setCursor(Qt.ArrowCursor)
                event.accept()
                return
        
        super().mouseReleaseEvent(event)
    
    def wheelEvent(self, event):
        """Zoom con rueda del mouse"""
        # Factor de zoom
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        # Guardar la posición del mouse en la escena antes del zoom
        old_pos = self.mapToScene(event.pos())
        
        # Aplicar zoom
        if event.angleDelta().y() > 0:
            # Zoom in
            zoom_factor = zoom_in_factor
            self.zoom_factor *= zoom_in_factor
        else:
            # Zoom out
            zoom_factor = zoom_out_factor
            self.zoom_factor *= zoom_out_factor
        
        # Limitar el zoom
        if self.zoom_factor < 0.1:
            self.zoom_factor = 0.1
            return
        elif self.zoom_factor > 10.0:
            self.zoom_factor = 10.0
            return
        
        # Aplicar la escala
        self.scale(zoom_factor, zoom_factor)
        
        # Obtener la nueva posición del mouse en la escena
        new_pos = self.mapToScene(event.pos())
        
        # Calcular la diferencia y ajustar la vista
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())


class BaloneaSimpleApp(QMainWindow):
    """Aplicación principal de baloneo simple"""
    
    def __init__(self):
        super().__init__()
        self.current_pdf_path = None
        self.current_page = 0
        self.total_pages = 0
        self.pdf_document = None
        self.unidad_global = "mm"
        self.balloon_counter = 0
        self.current_rotation = 0  # Rotación actual en grados (0, 90, 180, 270)
        self.original_pixmap = None  # Pixmap original sin rotar
        self.balloons_by_page = {}  # Diccionario para almacenar globos por página
        self.rotation_by_page = {}  # Diccionario para almacenar rotación por página
        
        # Aplicar estilo para QMessageBox directamente
        QApplication.instance().setStyleSheet("""
            QMessageBox {
                background-color: #000000;
            }
            QMessageBox QLabel {
                color: #000000 !important;
                font-size: 12px;
            }
            QMessageBox QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #1177bb;
            }
        """)
        
        self.init_ui()
    
    def parse_fraction_or_decimal(self, value_str):
        """
        Convertir string a decimal, aceptando fracciones (1/2, 3/4, etc.) o decimales (0.5, 1.25)
        Retorna el valor como float
        """
        if not value_str or value_str.strip() == '':
            return 0.0
        
        value_str = value_str.strip()
        
        try:
            # Intentar como fracción primero (puede tener números mixtos como "1 1/2")
            if '/' in value_str:
                # Manejar números mixtos (ej: "1 1/2" = 1.5)
                if ' ' in value_str:
                    parts = value_str.split()
                    whole = float(parts[0])
                    frac = Fraction(parts[1])
                    return whole + float(frac)
                else:
                    # Fracción simple (ej: "1/2" = 0.5)
                    return float(Fraction(value_str))
            else:
                # Número decimal normal
                return float(value_str)
        except (ValueError, ZeroDivisionError):
            return 0.0
        
    def init_ui(self):
        """Inicializar interfaz de usuario"""
        self.setWindowTitle('BALONEO SIMPLE')
        self.setGeometry(100, 100, 1600, 900)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #ffffff;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                padding: 8px 15px;
                font-size: 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:pressed {
                background-color: #0d5488;
            }
            QTableWidget {
                background-color: #252526;
                color: #ffffff;
                gridline-color: #3e3e42;
                border: 1px solid #3e3e42;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QTableWidget::item:selected {
                background-color: #094771;
            }
            QHeaderView::section {
                background-color: #2d2d30;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #3e3e42;
                font-weight: bold;
            }
            QLineEdit, QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555;
                padding: 5px;
                border-radius: 3px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #0e639c;
            }
            QGroupBox {
                color: #ffffff;
                border: 2px solid #3e3e42;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # === BARRA SUPERIOR ===
        top_bar = self.create_top_bar()
        main_layout.addLayout(top_bar)
        
        # === CONTENIDO PRINCIPAL (Splitter) ===
        splitter = QSplitter(Qt.Horizontal)
        
        # Panel izquierdo: Imagen con baloneo
        left_panel = self.create_image_panel()
        splitter.addWidget(left_panel)
        
        # Panel derecho: Tabla de dimensiones
        right_panel = self.create_dimensions_panel()
        splitter.addWidget(right_panel)
        
        # Configurar tamaños del splitter (70% imagen, 30% tabla)
        splitter.setSizes([1120, 480])
        main_layout.addWidget(splitter)
        
        # === BARRA INFERIOR ===
        bottom_bar = self.create_bottom_bar()
        main_layout.addLayout(bottom_bar)
        
    def create_top_bar(self):
        """Crear barra superior con controles principales"""
        layout = QHBoxLayout()
        
        # Botón cargar PDF
        btn_load = QPushButton('CARGAR PDF')
        btn_load.clicked.connect(self.load_pdf)
        btn_load.setStyleSheet("font-size: 14px; padding: 10px 20px;")
        layout.addWidget(btn_load)
        
        # Info del archivo
        self.lbl_file_info = QLabel('No hay archivo cargado')
        self.lbl_file_info.setStyleSheet("font-size: 13px; color: #aaa;")
        layout.addWidget(self.lbl_file_info)
        
        layout.addStretch()
        
        # Navegación de páginas
        self.btn_prev_page = QPushButton('◀ Anterior')
        self.btn_prev_page.clicked.connect(self.prev_page)
        self.btn_prev_page.setEnabled(False)
        layout.addWidget(self.btn_prev_page)
        
        self.lbl_page_info = QLabel('Página: 0/0')
        self.lbl_page_info.setStyleSheet("font-size: 12px; padding: 0 15px;")
        layout.addWidget(self.lbl_page_info)
        
        self.btn_next_page = QPushButton('Siguiente ▶')
        self.btn_next_page.clicked.connect(self.next_page)
        self.btn_next_page.setEnabled(False)
        layout.addWidget(self.btn_next_page)
        
        return layout
    
    def create_image_panel(self):
        """Crear panel de visualización de imagen"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Título
        title = QLabel('PLANO TÉCNICO - Clic: Agregar globo | Shift+Clic: Mover vista | Ctrl+Arrastrar: Mover globo')
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 5px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Vista de gráficos para baloneo
        self.graphics_view = BalloonGraphicsView(self)
        layout.addWidget(self.graphics_view)
        
        # Botones de acción
        action_layout = QHBoxLayout()
        
        btn_rotate = QPushButton('Rotar 90°')
        btn_rotate.clicked.connect(self.rotate_pdf)
        action_layout.addWidget(btn_rotate)
        
        btn_clear_balloons = QPushButton('Limpiar Globos')
        btn_clear_balloons.clicked.connect(self.clear_balloons)
        action_layout.addWidget(btn_clear_balloons)
        
        btn_remove_last = QPushButton('Eliminar Último')
        btn_remove_last.clicked.connect(self.remove_last_balloon)
        action_layout.addWidget(btn_remove_last)
        
        btn_zoom_fit = QPushButton('Ajustar Imagen')
        btn_zoom_fit.clicked.connect(self.zoom_fit)
        action_layout.addWidget(btn_zoom_fit)
        
        layout.addLayout(action_layout)
        
        return panel
    
    def create_dimensions_panel(self):
        """Crear panel de tabla de dimensiones"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # === Configuración Global ===
        config_group = QGroupBox('CONFIGURACIÓN GLOBAL')
        config_layout = QFormLayout()
        
        # Unidad global
        self.cmb_unidad = QComboBox()
        self.cmb_unidad.addItems(['mm', 'in'])
        self.cmb_unidad.currentTextChanged.connect(self.update_global_unit)
        self.cmb_unidad.setStyleSheet("background-color: #3c3c3c; color: #ffffff;")
        config_layout.addRow('Unidad:', self.cmb_unidad)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # === Contador de Baloneo ===
        counter_layout = QHBoxLayout()
        counter_layout.addWidget(QLabel('Globos:'))
        self.lbl_balloon_count = QLabel('0')
        self.lbl_balloon_count.setStyleSheet("""
            font-size: 28px; 
            font-weight: bold; 
            color: #4ec9b0;
            padding: 5px 15px;
            background-color: #2d2d30;
            border-radius: 5px;
        """)
        counter_layout.addWidget(self.lbl_balloon_count)
        counter_layout.addStretch()
        layout.addLayout(counter_layout)
        
        # === Tabla de Dimensiones ===
        table_label = QLabel('TABLA DE DIMENSIONES')
        table_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        layout.addWidget(table_label)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            'Nombre', 'Nominal', 'Tol +', 'Tol -', 'Instrumento', 'Unidad', 'Notas'
        ])
        
        # Configurar tamaño de columnas
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)        # Nombre
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # Nominal
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # Tol +
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # Tol -
        header.setSectionResizeMode(4, QHeaderView.Interactive)  # Instrumento
        header.setSectionResizeMode(5, QHeaderView.Fixed)        # Unidad
        header.setSectionResizeMode(6, QHeaderView.Stretch)      # Notas
        
        self.table.setColumnWidth(0, 60)   # Nombre
        self.table.setColumnWidth(1, 80)   # Nominal
        self.table.setColumnWidth(2, 60)   # Tol +
        self.table.setColumnWidth(3, 60)   # Tol -
        self.table.setColumnWidth(4, 100)  # Instrumento
        self.table.setColumnWidth(5, 60)   # Unidad
        
        layout.addWidget(self.table)
        
        # Botones de tabla
        table_buttons = QHBoxLayout()
        
        btn_delete_row = QPushButton('Eliminar Fila Seleccionada')
        btn_delete_row.clicked.connect(self.delete_dimension_row)
        table_buttons.addWidget(btn_delete_row)
        
        btn_clear_table = QPushButton('Limpiar Tabla')
        btn_clear_table.clicked.connect(self.clear_table)
        table_buttons.addWidget(btn_clear_table)
        
        layout.addLayout(table_buttons)
        
        return panel
    
    def create_bottom_bar(self):
        """Crear barra inferior con botones de exportación"""
        layout = QHBoxLayout()
        
        layout.addStretch()
        
        # Botón exportar PDF con globos
        btn_export_pdf = QPushButton('EXPORTAR PDF CON GLOBOS')
        btn_export_pdf.setStyleSheet("""
            font-size: 16px; 
            padding: 12px 30px;
            background-color: #2980b9;
        """)
        btn_export_pdf.clicked.connect(self.export_pdf_with_balloons)
        layout.addWidget(btn_export_pdf)

        layout.addStretch()
        
        return layout
    
    # === FUNCIONES DE CARGA DE PDF ===
    
    def load_pdf(self):
        """Cargar archivo PDF"""
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Seleccionar PDF', '', 'PDF Files (*.pdf);;All Files (*.*)'
        )
        
        if file_path:
            try:
                self.pdf_document = fitz.open(file_path)
                self.current_pdf_path = file_path
                self.total_pages = len(self.pdf_document)
                self.current_page = 0
                
                # Resetear rotación al cargar nuevo PDF
                self.current_rotation = 0
                self.original_pixmap = None
                
                # Actualizar info
                file_name = Path(file_path).name
                self.lbl_file_info.setText(f'{file_name}')
                
                # Habilitar navegación
                self.btn_next_page.setEnabled(self.total_pages > 1)
                self.btn_prev_page.setEnabled(False)
                
                # Mostrar primera página
                self.show_current_page()
                
            except Exception as e:
                QMessageBox.critical(self, 'Error', f'Error al cargar PDF:\n{e}')
    
    def show_current_page(self):
        """Mostrar página actual del PDF"""
        if not self.pdf_document:
            return
        
        try:
            # Obtener página
            page = self.pdf_document[self.current_page]
            
            # Renderizar a imagen con alta resolución
            zoom = 2.0  # Factor de zoom para mejor calidad
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Convertir a QImage
            img_data = pix.samples
            img = QImage(img_data, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            
            # Convertir a QPixmap y cargar en vista
            pixmap = QPixmap.fromImage(img)
            self.graphics_view.load_image(pixmap)
            
            # Restaurar rotación de esta página (si existe)
            self.current_rotation = self.rotation_by_page.get(self.current_page, 0)
            self.original_pixmap = None
            
            # Si hay rotación guardada, aplicarla
            if self.current_rotation != 0:
                self.original_pixmap = pixmap
                transform = QTransform()
                transform.rotate(self.current_rotation)
                rotated_pixmap = self.original_pixmap.transformed(transform, Qt.SmoothTransformation)
                self.graphics_view.pixmap_item.setPixmap(rotated_pixmap)
                self.graphics_view.fitInView(self.graphics_view.pixmap_item, Qt.KeepAspectRatio)
            
            # Actualizar info de página
            self.lbl_page_info.setText(f'Página: {self.current_page + 1}/{self.total_pages}')
            
            # Actualizar botones de navegación
            self.btn_prev_page.setEnabled(self.current_page > 0)
            self.btn_next_page.setEnabled(self.current_page < self.total_pages - 1)
            
            # Restaurar globos de esta página
            self.restore_balloons_for_current_page()
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Error al mostrar página:\n{e}')
    
    def prev_page(self):
        """Página anterior"""
        if self.current_page > 0:
            self.save_balloons_for_current_page()
            self.current_page -= 1
            self.show_current_page()
    
    def next_page(self):
        """Página siguiente"""
        if self.current_page < self.total_pages - 1:
            self.save_balloons_for_current_page()
            self.current_page += 1
            self.show_current_page()
    
    def save_balloons_for_current_page(self):
        """Guardar globos y tabla de la página actual"""
        # Guardar globos visuales
        balloons_data = []
        for balloon in self.graphics_view.balloon_items:
            balloons_data.append({
                'x': balloon['x'],
                'y': balloon['y'],
                'number': balloon['number'],
                'size': balloon['size'],
                'rotation': balloon.get('rotation', 0)
            })
        
        # Guardar datos de la tabla
        table_data = []
        for i in range(self.table.rowCount()):
            nombre = self.table.item(i, 0).text() if self.table.item(i, 0) else f'D{i+1}'
            nominal = self.table.item(i, 1).text() if self.table.item(i, 1) else '0.0'
            tol_pos = self.table.item(i, 2).text() if self.table.item(i, 2) else '0.0'
            tol_neg = self.table.item(i, 3).text() if self.table.item(i, 3) else '0.0'
            cmb_widget = self.table.cellWidget(i, 4)
            instrumento = cmb_widget.currentText() if cmb_widget else 'Vernier'
            unidad = self.table.item(i, 5).text() if self.table.item(i, 5) else 'mm'
            notas = self.table.item(i, 6).text() if self.table.item(i, 6) else ''
            
            table_data.append({
                'nombre': nombre,
                'nominal': nominal,
                'tol_pos': tol_pos,
                'tol_neg': tol_neg,
                'instrumento': instrumento,
                'unidad': unidad,
                'notas': notas
            })
        
        # Guardar en el diccionario
        self.balloons_by_page[self.current_page] = {
            'balloons': balloons_data,
            'table': table_data,
            'counter': self.balloon_counter
        }
        
        # Guardar rotación
        self.rotation_by_page[self.current_page] = self.current_rotation
    
    def restore_balloons_for_current_page(self):
        """Restaurar globos y tabla de la página actual"""
        # Limpiar vista actual
        self.graphics_view.clear_balloons()
        self.table.setRowCount(0)
        
        # Verificar si hay datos guardados para esta página
        if self.current_page in self.balloons_by_page:
            page_data = self.balloons_by_page[self.current_page]
            
            # Restaurar globos visuales
            for balloon_data in page_data['balloons']:
                self.graphics_view.add_balloon(
                    balloon_data['x'],
                    balloon_data['y'],
                    balloon_data['number'],
                    balloon_data['size']
                )
            
            # Restaurar tabla
            for row_data in page_data['table']:
                row_count = self.table.rowCount()
                self.table.insertRow(row_count)
                
                self.table.setItem(row_count, 0, QTableWidgetItem(row_data['nombre']))
                self.table.setItem(row_count, 1, QTableWidgetItem(row_data['nominal']))
                self.table.setItem(row_count, 2, QTableWidgetItem(row_data['tol_pos']))
                self.table.setItem(row_count, 3, QTableWidgetItem(row_data['tol_neg']))
                
                cmb_instrumento = QComboBox()
                cmb_instrumento.addItems(['Vernier', 'Micrómetro', 'Calibrador', 'Probador', 'CMM', 'Comparador', 'Otro'])
                cmb_instrumento.setCurrentText(row_data['instrumento'])
                cmb_instrumento.setStyleSheet("background-color: #3c3c3c; color: #ffffff;")
                self.table.setCellWidget(row_count, 4, cmb_instrumento)
                
                unidad_item = QTableWidgetItem(row_data['unidad'])
                unidad_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                unidad_item.setBackground(QColor(60, 60, 60))
                self.table.setItem(row_count, 5, unidad_item)
                
                self.table.setItem(row_count, 6, QTableWidgetItem(row_data['notas']))
            
            # Restaurar contador
            self.balloon_counter = page_data['counter']
        else:
            # Página nueva, resetear contador
            self.balloon_counter = 0
        
        self.update_balloon_counter()
    
    def rotate_pdf(self):
        """Rotar PDF 90 grados en sentido horario"""
        if not self.pdf_document or not self.graphics_view.pixmap_item:
            return
        
        try:
            # Guardar el pixmap original si no existe
            if self.original_pixmap is None:
                self.original_pixmap = self.graphics_view.pixmap_item.pixmap()
            
            # Incrementar rotación (0 -> 90 -> 180 -> 270 -> 0)
            self.current_rotation = (self.current_rotation + 90) % 360
            
            # Crear transformación de rotación con el ángulo total acumulado
            transform = QTransform()
            transform.rotate(self.current_rotation)
            
            # Aplicar rotación al pixmap original
            rotated_pixmap = self.original_pixmap.transformed(transform, Qt.SmoothTransformation)
            
            # Actualizar la vista con el pixmap rotado
            self.graphics_view.pixmap_item.setPixmap(rotated_pixmap)
            
            # Ajustar la vista para mostrar toda la imagen rotada
            self.graphics_view.fitInView(self.graphics_view.pixmap_item, Qt.KeepAspectRatio)
            
            # Rotar también la página del PDF para que se guarde rotado
            page = self.pdf_document[self.current_page]
            page.set_rotation(self.current_rotation)
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Error al rotar PDF:\n{e}')
    
    # === FUNCIONES DE BALONEO ===
    
    def on_image_click(self, x, y):
        """Callback cuando se hace clic en la imagen"""
        # Incrementar contador
        self.balloon_counter += 1
        
        # Agregar globo visual en la imagen
        self.graphics_view.add_balloon(x, y, self.balloon_counter)
        
        # Agregar fila a la tabla
        self.add_dimension_row(self.balloon_counter)
        
        # Actualizar contador visual
        self.update_balloon_counter()
    
    def update_balloon_counter(self):
        """Actualizar el contador visual de globos"""
        self.lbl_balloon_count.setText(str(self.balloon_counter))
    
    def clear_balloons(self):
        """Limpiar todos los globos"""
        if self.balloon_counter == 0:
            return
        
        reply = QMessageBox.question(
            self, '¿Limpiar Globos?',
            '¿Está seguro de limpiar todos los globos?\n'
            'Esto también limpiará la tabla de dimensiones.',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.graphics_view.clear_balloons()
            self.table.setRowCount(0)
            self.balloon_counter = 0
            self.update_balloon_counter()
    
    def remove_last_balloon(self):
        """Eliminar el último globo agregado"""
        if self.balloon_counter > 0:
            # Eliminar de la vista
            self.graphics_view.remove_balloon(self.balloon_counter - 1)
            
            # Eliminar última fila de la tabla
            if self.table.rowCount() > 0:
                self.table.removeRow(self.table.rowCount() - 1)
            
            # Decrementar contador
            self.balloon_counter -= 1
            self.update_balloon_counter()
    
    def zoom_fit(self):
        """Ajustar imagen al tamaño de la vista"""
        if self.graphics_view.pixmap_item:
            self.graphics_view.fitInView(self.graphics_view.pixmap_item, Qt.KeepAspectRatio)
    
    # === FUNCIONES DE TABLA ===
    
    def add_dimension_row(self, balloon_number):
        """Agregar nueva fila a la tabla de dimensiones"""
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        
        # Nombre (basado en el número de globo) - EDITABLE
        nombre_item = QTableWidgetItem(f'D{balloon_number}')
        self.table.setItem(row_count, 0, nombre_item)
        
        # Nominal
        nominal_item = QTableWidgetItem('0.0')
        self.table.setItem(row_count, 1, nominal_item)
        
        # Tolerancia +
        tol_pos_item = QTableWidgetItem('0.0')
        self.table.setItem(row_count, 2, tol_pos_item)
        
        # Tolerancia -
        tol_neg_item = QTableWidgetItem('0.0')
        self.table.setItem(row_count, 3, tol_neg_item)
        
        # Instrumento (ComboBox)
        cmb_instrumento = QComboBox()
        cmb_instrumento.addItems(['Vernier', 'Micrómetro', 'Calibrador', 'Probador', 'CMM', 'Comparador', 'Otro'])
        cmb_instrumento.setStyleSheet("background-color: #3c3c3c; color: #ffffff;")
        self.table.setCellWidget(row_count, 4, cmb_instrumento)
        
        # Unidad
        unidad_item = QTableWidgetItem(self.unidad_global)
        unidad_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)  # No editable
        unidad_item.setBackground(QColor(60, 60, 60))
        self.table.setItem(row_count, 5, unidad_item)
        
        # Notas
        notas_item = QTableWidgetItem('')
        self.table.setItem(row_count, 6, notas_item)
    
    def delete_dimension_row(self):
        """Eliminar fila seleccionada"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            reply = QMessageBox.question(
                self, '¿Eliminar Fila?',
                f'¿Está seguro de eliminar la fila {current_row + 1}?',
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.table.removeRow(current_row)
                # También eliminar el globo correspondiente
                if current_row < len(self.graphics_view.balloon_items):
                    self.graphics_view.remove_balloon(current_row)
                    self.balloon_counter -= 1
                    self.update_balloon_counter()
    
    def clear_table(self):
        """Limpiar toda la tabla"""
        if self.table.rowCount() == 0:
            return
        
        reply = QMessageBox.question(
            self, '¿Limpiar Tabla?',
            '¿Está seguro de eliminar todas las filas?\nEsto también eliminará todos los globos.',
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.table.setRowCount(0)
            self.graphics_view.clear_balloons()
            self.balloon_counter = 0
            self.update_balloon_counter()
    
    def update_global_unit(self, unit):
        """Actualizar unidad global en todas las filas"""
        self.unidad_global = unit
        for i in range(self.table.rowCount()):
            if self.table.item(i, 5):
                self.table.item(i, 5).setText(unit)
    
    # === FUNCIONES DE EXPORTACIÓN/IMPORTACIÓN ===
    
    def export_json(self):
        """Exportar dimensiones a JSON en el formato especificado"""
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, 'Tabla Vacía', 
                              'No hay dimensiones para exportar.')
            return
        
        # Solicitar ubicación de guardado
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Guardar JSON', '', 'JSON Files (*.json)'
        )
        
        if not file_path:
            return
        
        try:
            # Recolectar datos de la tabla
            dimensiones = []
            for i in range(self.table.rowCount()):
                nombre = self.table.item(i, 0).text() if self.table.item(i, 0) else f'D{i+1}'
                
                # Parsear valores aceptando fracciones o decimales
                nominal = self.parse_fraction_or_decimal(
                    self.table.item(i, 1).text() if self.table.item(i, 1) else '0'
                )
                
                tol_pos = self.parse_fraction_or_decimal(
                    self.table.item(i, 2).text() if self.table.item(i, 2) else '0'
                )
                
                tol_neg = self.parse_fraction_or_decimal(
                    self.table.item(i, 3).text() if self.table.item(i, 3) else '0'
                )
                
                # Obtener instrumento del ComboBox
                cmb_widget = self.table.cellWidget(i, 4)
                instrumento = cmb_widget.currentText() if cmb_widget else 'Vernier'
                
                unidad = self.table.item(i, 5).text() if self.table.item(i, 5) else 'mm'
                notas = self.table.item(i, 6).text() if self.table.item(i, 6) else ''
                
                dimensiones.append({
                    'nombre': nombre,
                    'nominal': nominal,
                    'tol_pos': tol_pos,
                    'tol_neg': tol_neg,
                    'instrumento': instrumento,
                    'unidad': unidad,
                    'notas': notas
                })
            
            # Crear estructura JSON en el formato especificado
            data = {
                'dimensiones': dimensiones,
                'version': 1,
                'fecha_creacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # Guardar archivo
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self, 'Exportación Exitosa',
                                  f'✅ Archivo exportado correctamente:\n{file_path}\n\n'
                                  f'📊 {len(dimensiones)} dimensiones guardadas\n'
                                  f' Fecha: {data["fecha_creacion"]}')
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Error al exportar:\n{e}')
    
    def export_pdf_with_balloons(self):
        """Exportar PDF con globos dibujados y JSON de dimensiones"""
        
        # Validar que hay dimensiones
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, 'Sin dimensiones', 
                              'No hay dimensiones para exportar.\n'
                              'Agregue al menos una dimensión antes de exportar.')
            return
        
        # Validar que hay PDF cargado
        if not self.current_pdf_path or not self.pdf_document:
            QMessageBox.warning(self, 'Sin PDF', 
                              'No hay PDF cargado.\n'
                              'Cargue un PDF antes de exportar.')
            return
        
        try:
            # Solicitar nombre base para los archivos
            default_name = Path(self.current_pdf_path).stem + '_baloneado'
            file_path, _ = QFileDialog.getSaveFileName(
                self, 'Guardar PDF con Globos', default_name, 'PDF Files (*.pdf)'
            )
            
            if not file_path:
                return
            
            # Asegurar extensión .pdf
            if not file_path.lower().endswith('.pdf'):
                file_path += '.pdf'
            
            # Crear archivo PDF con globos
            pdf_bytes = self.generate_pdf_with_balloons()
            
            if not pdf_bytes:
                QMessageBox.warning(self, 'Error', 'No se pudo generar el PDF con globos')
                return
            
            # Guardar PDF
            with open(file_path, 'wb') as f:
                f.write(pdf_bytes)
            
            # Guardar JSON con el mismo nombre base
            json_path = Path(file_path).with_suffix('.json')
            dimensions_json = self.generate_dimensions_json()
            
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(dimensions_json)
            
            QMessageBox.information(self, 'Exportación Exitosa',
                                  f'Archivos exportados correctamente:\n\n'
                                  f'PDF: {file_path}\n'
                                  f'JSON: {json_path}\n\n'
                                  f'{self.balloon_counter} globos dibujados\n'
                                  f'{self.table.rowCount()} dimensiones guardadas')
            
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Error al exportar:\n{e}')
            import traceback
            traceback.print_exc()
    
    def generate_dimensions_json(self):
        """Generar JSON de dimensiones en formato string"""
        dimensiones = []
        
        for i in range(self.table.rowCount()):
            nombre = self.table.item(i, 0).text() if self.table.item(i, 0) else f'D{i+1}'
            
            # Parsear valores aceptando fracciones o decimales
            nominal = self.parse_fraction_or_decimal(
                self.table.item(i, 1).text() if self.table.item(i, 1) else '0'
            )
            
            tol_pos = self.parse_fraction_or_decimal(
                self.table.item(i, 2).text() if self.table.item(i, 2) else '0'
            )
            
            tol_neg = self.parse_fraction_or_decimal(
                self.table.item(i, 3).text() if self.table.item(i, 3) else '0'
            )
            
            # Obtener instrumento del ComboBox
            cmb_widget = self.table.cellWidget(i, 4)
            instrumento = cmb_widget.currentText() if cmb_widget else 'Vernier'
            
            unidad = self.table.item(i, 5).text() if self.table.item(i, 5) else 'mm'
            notas = self.table.item(i, 6).text() if self.table.item(i, 6) else ''
            
            dimensiones.append({
                'nombre': nombre,
                'nominal': nominal,
                'tol_pos': tol_pos,
                'tol_neg': tol_neg,
                'instrumento': instrumento,
                'unidad': unidad,
                'notas': notas
            })
        
        # Crear estructura JSON
        data = {
            'dimensiones': dimensiones,
            'version': 1,
            'fecha_creacion': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Convertir a string JSON
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def generate_pdf_with_balloons(self):
        """Generar PDF con los globos dibujados en todas las páginas"""
        try:
            if not self.pdf_document:
                return None
            
            # Guardar la página actual antes de exportar
            self.save_balloons_for_current_page()
            
            # Crear un nuevo PDF temporal con los globos dibujados
            import tempfile
            import os
            
            # Crear primer archivo temporal para el PDF original
            temp_fd1, temp_path1 = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd1)
            
            # Aplicar todas las rotaciones guardadas antes de guardar
            for page_num, rotation in self.rotation_by_page.items():
                if rotation != 0:
                    page = self.pdf_document[page_num]
                    page.set_rotation(rotation)
            
            # Guardar el PDF actual (con rotaciones aplicadas)
            self.pdf_document.save(temp_path1)
            
            # Reabrir el PDF guardado para dibujar los globos
            temp_doc = fitz.open(temp_path1)
            
            # Procesar cada página que tenga globos
            for page_num, page_data in self.balloons_by_page.items():
                if page_num >= len(temp_doc):
                    continue
                    
                page = temp_doc[page_num]
                balloons = page_data['balloons']
                
                if len(balloons) == 0:
                    continue
                
                self.draw_balloons_on_page(page, balloons, page_num)
            
            # Crear segundo archivo temporal para guardar el PDF modificado
            temp_fd2, temp_path2 = tempfile.mkstemp(suffix='.pdf')
            os.close(temp_fd2)
            
            # Guardar el PDF modificado en el segundo archivo temporal
            temp_doc.save(temp_path2)
            temp_doc.close()
            
            # Leer el PDF modificado
            with open(temp_path2, 'rb') as f:
                pdf_bytes = f.read()
            
            # Eliminar archivos temporales
            try:
                os.unlink(temp_path1)
                os.unlink(temp_path2)
            except:
                pass  # Ignorar errores al eliminar archivos temporales
            
            print(f"DEBUG - PDF generado con {len(pdf_bytes)} bytes")
            
            return pdf_bytes
            
        except Exception as e:
            print(f"Error generando PDF con globos: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def draw_balloons_on_page(self, page, balloons, page_num):
        """Dibujar globos en una página específica del PDF"""
        # Obtener dimensiones de la página ORIGINAL (antes de rotación)
        # La página ya tiene la rotación aplicada, pero necesitamos las dimensiones originales
        page_rect = page.rect
        page_width = page_rect.width
        page_height = page_rect.height
        
        # Factor de zoom usado al renderizar el PDF (en show_current_page)
        render_zoom = 2.0
        
        # Obtener rotación de la página
        rotation = page.rotation
        
        print(f"DEBUG PDF Página {page_num+1} - Después de rotación: {page_width}x{page_height}")
        print(f"DEBUG - Rotación de página: {rotation}°")
        print(f"DEBUG - Globos a dibujar: {len(balloons)}")
        
        # Calcular dimensiones originales (antes de rotar)
        if rotation in [90, 270]:
            # Si está rotado 90° o 270°, las dimensiones están intercambiadas
            original_width = page_height
            original_height = page_width
        else:
            original_width = page_width
            original_height = page_height
        
        print(f"DEBUG - Dimensiones originales: {original_width}x{original_height}")
        
        # Dibujar cada globo en el PDF
        for i, balloon in enumerate(balloons):
            # Las coordenadas x, y están en el sistema de coordenadas de la escena
            # que corresponde a la imagen ROTADA renderizada a 2.0x
            x = balloon['x']
            y = balloon['y']
            number = balloon['number']
            size = balloon['size']
            balloon_rotation = balloon.get('rotation', 0)  # Rotación cuando se agregó el globo
            
            print(f"DEBUG Globo {number} - Escena: ({x:.1f}, {y:.1f}), Tamaño: {size}, Rotación guardada: {balloon_rotation}°")
            
            # Convertir coordenadas de la imagen renderizada (dividir por zoom)
            screen_x = x / render_zoom
            screen_y = y / render_zoom
            
            # Dimensiones de la imagen renderizada rotada
            if rotation in [90, 270]:
                rendered_width = page_height
                rendered_height = page_width
            else:
                rendered_width = page_width
                rendered_height = page_height
            
            print(f"DEBUG Globo {number} - Coords pantalla: ({screen_x:.1f}, {screen_y:.1f})")
            print(f"DEBUG - Dimensiones para transformación: original={original_width}x{original_height}, rotada={page_width}x{page_height}")
            
            # Transformar coordenadas según la rotación
            # IMPORTANTE: Las coordenadas en pantalla van en el sistema rotado
            # Necesitamos convertirlas al sistema PDF original
            if rotation == 0:
                # Sin rotación - solo usar las coordenadas directamente
                pdf_x = screen_x
                pdf_y = screen_y
            elif rotation == 90:
                # 90° horario: La imagen rotó, así que transformamos
                # En pantalla vemos (x,y) pero en PDF original es:
                # La coordenada X de pantalla se convierte en Y de PDF
                # La coordenada Y de pantalla se convierte en (original_width - X) de PDF
                pdf_x = screen_y
                pdf_y = page_width - screen_x
            elif rotation == 180:
                # 180°: Volteado completamente
                pdf_x = page_width - screen_x
                pdf_y = page_height - screen_y
            elif rotation == 270:
                # 270° horario (o 90° antihorario)
                # X pantalla → (original_height - Y) PDF
                # Y pantalla → X PDF  
                pdf_x = page_height - screen_y
                pdf_y = screen_x
            else:
                pdf_x = screen_x
                pdf_y = screen_y
            
            pdf_radius = (size / 2.0) / render_zoom
            
            print(f"DEBUG Globo {number} - PDF final: ({pdf_x:.1f}, {pdf_y:.1f}), Radio: {pdf_radius:.1f}")
            
            # Dibujar círculo con relleno
            page.draw_circle(
                (pdf_x, pdf_y), 
                pdf_radius, 
                color=(0, 0.47, 0.84),  # Azul
                width=2.5,  # Línea gruesa
                fill=(0, 0.47, 0.84),  # Relleno azul
                fill_opacity=0.4
            )
            
            # Calcular el tamaño de fuente
            fontsize = pdf_radius * 1.2
            
            # Insertar texto centrado en el globo - ROTANDO JUNTO CON LA PÁGINA
            text = str(number)
            
            # Calcular el tamaño aproximado del texto
            text_width = fitz.get_text_length(text, fontname="helv", fontsize=fontsize)
            text_height = fontsize
            
            # Usar el centro del globo como punto de anclaje para la rotación
            # y ajustar desde ahí según la rotación
            if rotation == 0:
                # Sin rotación - centrado normal
                text_x = pdf_x - (text_width / 2)
                text_y = pdf_y + (text_height / 3)
            elif rotation == 90:
                # Rotado 90° horario
                text_x = pdf_x + (text_height / 3)
                text_y = pdf_y + (text_width / 2)
            elif rotation == 180:
                # Rotado 180°
                text_x = pdf_x + (text_width / 2)
                text_y = pdf_y - (text_height / 3)
            elif rotation == 270:
                # Rotado 270° horario (90° antihorario)
                text_x = pdf_x - (text_height / 3)
                text_y = pdf_y - (text_width / 2)
            else:
                text_x = pdf_x - (text_width / 2)
                text_y = pdf_y + (text_height / 3)
            
            # Aplicar la MISMA rotación que la página para que el texto rote junto con ella
            try:
                page.insert_text(
                    (text_x, text_y),
                    text,
                    fontsize=fontsize,
                    color=(1, 1, 1),  # Blanco
                    fontname="helv",
                    rotate=rotation,  # MISMA rotación que la página
                    overlay=True
                )
                
                print(f"DEBUG Globo {number} - Texto insertado en ({text_x:.1f}, {text_y:.1f}) rotando {rotation}°")
                
            except Exception as e:
                print(f"ERROR insertando texto en globo {number}: {e}")
                import traceback
                traceback.print_exc()


def main():
    """Función principal"""
    app = QApplication(sys.argv)
    
    # Configurar estilo de la aplicación
    app.setStyle('Fusion')
    
    # Configurar estilo para QMessageBox con texto negro visible
    app.setStyleSheet("""
        QMessageBox {
            background-color: #f0f0f0;
        }
        QMessageBox QLabel {
            color: #000000;
            font-size: 12px;
        }
        QMessageBox QPushButton {
            background-color: #0e639c;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 4px;
            font-weight: bold;
            min-width: 80px;
        }
        QMessageBox QPushButton:hover {
            background-color: #1177bb;
        }
    """)
    
    window = BaloneaSimpleApp()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
