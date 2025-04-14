
# ========== 界面组件 ==========

import sys
import numpy as np
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QObject
from PyQt5.QtCore import QSignalBlocker 
from PyQt5.QtGui import QKeySequence
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import QModelIndex, QItemSelectionModel
from Raycaster import GeometryRaycaster, RaycastResult
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *
import xml.etree.ElementTree as ET
from PyQt5.QtWidgets import QColorDialog  # 对话框类在QtWidgets模块
from PyQt5.QtGui import QColor            # 颜色类在QtGui模块        
from PyQt5.QtGui import QPixmap  # 新增这行
from PyQt5.QtGui import QDrag
from PyQt5.QtCore import Qt, QMimeData  # QMimeData 在 QtCore 中
from PyQt5.QtGui import QIcon

from Geomentry import TransformMode, Material, GeometryType as OriginalGeometryType, Geometry, OperationMode
from Geomentry import GeometryGroup

class GeometryType(OriginalGeometryType):
    if not hasattr(OriginalGeometryType, 'ELLIPSOID'):
        ELLIPSOID = 'ellipsoid'

if not hasattr(GeometryType, 'ELLIPSOID'):
    setattr(GeometryType, 'ELLIPSOID', 'ellipsoid')



class ControlPanel(QDockWidget):
    def __init__(self, gl_widget):
        super().__init__("控制面板")
        self.gl_widget = gl_widget
        
        # 创建控制面板主窗口
        main_widget = QWidget()
        layout = QVBoxLayout(main_widget)
        
        # 创建几何体类型选择框
        geo_type_group = QGroupBox("添加几何体")
        geo_type_layout = QGridLayout()
        
        # 几何体类型和名称映射
        geo_types = [
            (GeometryType.BOX, "立方体"),
            (GeometryType.SPHERE, "球体"),
            (GeometryType.ELLIPSOID, "椭球体"),
            (GeometryType.CYLINDER, "圆柱体"),
            (GeometryType.CAPSULE, "胶囊体"),
            (GeometryType.PLANE, "平面")
        ]
        
        # 创建可拖拽按钮
        row, col = 0, 0
        for geo_type, title in geo_types:
            btn = DraggableGeometryButton(geo_type, title)
            geo_type_layout.addWidget(btn, row, col)
            col += 1
            if col > 1:  # 每行两个按钮
                col = 0
                row += 1
        
        # 保留常规的下拉框和添加按钮
        row += 1
        self.geo_type_combo = QComboBox()
        self.geo_type_combo.addItems([f"{title} ({geo_type})" for geo_type, title in geo_types])
        geo_type_layout.addWidget(self.geo_type_combo, row, 0, 1, 2)
        
        row += 1
        add_btn = QPushButton("添加所选几何体")
        add_btn.clicked.connect(self.add_geometry)
        geo_type_layout.addWidget(add_btn, row, 0, 1, 2)
        
        # 添加拖拽提示标签
        row += 1
        drag_label = QLabel("提示: 拖拽按钮到3D视图中放置物体")
        drag_label.setAlignment(Qt.AlignCenter)
        drag_label.setStyleSheet("color: gray; font-style: italic;")
        geo_type_layout.addWidget(drag_label, row, 0, 1, 2)
        
        geo_type_group.setLayout(geo_type_layout)
        layout.addWidget(geo_type_group)
        
        # 操作模式选择
        mode_group = QGroupBox("操作模式")
        mode_layout = QVBoxLayout()
        
        # 添加不同的操作模式按钮
        self.observe_btn = QRadioButton("观察模式")
        self.translate_btn = QRadioButton("平移模式")
        self.rotate_btn = QRadioButton("旋转模式")
        self.scale_btn = QRadioButton("缩放模式")
        
        self.observe_btn.setChecked(True)
        
        # 连接信号
        self.observe_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_OBSERVE))
        self.translate_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_TRANSLATE))
        self.rotate_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_ROTATE))
        self.scale_btn.toggled.connect(lambda: self.on_mode_changed(OperationMode.MODE_SCALE))
        
        # 添加到布局
        mode_layout.addWidget(self.observe_btn)
        mode_layout.addWidget(self.translate_btn)
        mode_layout.addWidget(self.rotate_btn)
        mode_layout.addWidget(self.scale_btn)
        
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)
        
        # 添加视图设置组
        view_group = QGroupBox("视图设置")
        view_layout = QVBoxLayout()
        
        ortho_check = QCheckBox("正交投影")
        ortho_check.toggled.connect(self.toggle_ortho)
        view_layout.addWidget(ortho_check)
        
        view_group.setLayout(view_layout)
        layout.addWidget(view_group)
        
        # 添加伸缩项填充剩余空间
        layout.addStretch()
        
        # 设置主窗口
        self.setWidget(main_widget)
    
    def add_geometry(self):
        """根据下拉框选择添加不同类型的几何体，注意使用 Mujoco 半尺寸标准"""
        type_index = self.geo_type_combo.currentIndex()
        geo_type = [
            GeometryType.BOX, 
            GeometryType.SPHERE, 
            GeometryType.ELLIPSOID,
            GeometryType.CYLINDER,
            GeometryType.CAPSULE,
            GeometryType.PLANE
        ][type_index]
        
        # 为不同类型设置合适的默认尺寸（半长半宽半高）
        default_sizes = {
            GeometryType.BOX: (0.5, 0.5, 0.5),         # 半长半宽半高
            GeometryType.SPHERE: (0.5, 0.5, 0.5),      # 半径
            GeometryType.ELLIPSOID: (0.6, 0.4, 0.3),   # 三轴半径
            GeometryType.CYLINDER: (0.5, 0.5, 0.5),    # 半径, 半高
            GeometryType.CAPSULE: (0.5, 0.5, 0.5),     # 半径, 半高
            GeometryType.PLANE: (1.0, 1.0, 0.05)       # 半宽, 半长, 半厚
        }
        
        # 为不同类型设置默认名称
        type_names = {
            GeometryType.BOX: "立方体",
            GeometryType.SPHERE: "球体",
            GeometryType.ELLIPSOID: "椭球体",
            GeometryType.CYLINDER: "圆柱体",
            GeometryType.CAPSULE: "胶囊体",
            GeometryType.PLANE: "平面"
        }
        
        # 创建几何体
        count = sum(1 for geo in self.gl_widget.geometries if geo.type == geo_type)
        name = f"{type_names[geo_type]}_{count+1}"
        size = default_sizes[geo_type]
        
        # 创建几何体对象
        geo = Geometry(
            geo_type=geo_type,
            name=name,
            position=(0, 0, 0),
            size=size,
            rotation=(0, 0, 0)
        )
        
        # 添加到场景
        self.gl_widget.add_geometry(geo)
        
        # 选中新添加的几何体
        self.gl_widget.set_selection(geo)
        
        # 如果在观察模式，自动切换到平移模式
        if self.gl_widget.current_mode == OperationMode.MODE_OBSERVE:
            self.translate_btn.setChecked(True)
    
    def on_mode_changed(self, mode_id):
        """处理操作模式变更"""
        if self.sender().isChecked():  # 只在按钮被选中时处理
            self.gl_widget.set_operation_mode(mode_id)
    
    def toggle_ortho(self, checked):
        """切换正交/透视投影"""
        self.gl_widget.use_orthographic = checked
        self.gl_widget.update_camera_config()

    def update_mode_buttons(self, mode_id):
        """根据当前模式更新按钮状态"""
        # 阻断信号以避免循环触发
        with QSignalBlocker(self.observe_btn), QSignalBlocker(self.translate_btn), \
             QSignalBlocker(self.rotate_btn), QSignalBlocker(self.scale_btn):
            
            self.observe_btn.setChecked(mode_id == OperationMode.MODE_OBSERVE)
            self.translate_btn.setChecked(mode_id == OperationMode.MODE_TRANSLATE)
            self.rotate_btn.setChecked(mode_id == OperationMode.MODE_ROTATE)
            self.scale_btn.setChecked(mode_id == OperationMode.MODE_SCALE)

class DraggableGeometryButton(QPushButton):
    """可拖拽的几何体创建按钮"""
    def __init__(self, geo_type, title, parent=None):
        super().__init__(title, parent)
        self.geo_type = geo_type
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        
    def mousePressEvent(self, event):
        """开始拖拽"""
        if event.button() == Qt.LeftButton:
            # 创建拖拽对象
            drag = QDrag(self)
            mime_data = QMimeData()
            
            # 存储几何体类型
            mime_data.setText(self.geo_type)
            drag.setMimeData(mime_data)
            
            # 创建拖拽时的预览图像
            pixmap = QPixmap(self.size())
            self.render(pixmap)
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            
            # 开始拖拽
            drag.exec_(Qt.CopyAction)
        else:
            super().mousePressEvent(event)