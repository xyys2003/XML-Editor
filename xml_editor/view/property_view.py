"""
属性视图

负责显示和编辑选中对象的属性。
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel, 
                            QLineEdit, QDoubleSpinBox, QComboBox, QColorDialog,
                            QPushButton, QHBoxLayout, QGroupBox, QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor

import numpy as np

from ..model.geometry import GeometryType, Material

class PropertyView(QWidget):
    """
    属性视图类
    
    用于显示和编辑选中对象的属性
    """
    # 信号：当属性被修改时发出
    propertyChanged = pyqtSignal(str, object)
    
    def __init__(self, property_viewmodel, parent=None):
        """
        初始化属性视图
        
        参数:
            property_viewmodel: 属性视图模型的引用
            parent: 父窗口部件
        """
        super().__init__(parent)
        self._property_viewmodel = property_viewmodel
        
        # 监听视图模型的变化
        self._property_viewmodel.propertiesChanged.connect(self._update_ui)
        
        # 创建UI
        self._init_ui()
    
    def _init_ui(self):
        """初始化用户界面"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        
        # 标题标签
        self._title_label = QLabel("未选择对象")
        self._title_label.setAlignment(Qt.AlignCenter)
        self._title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self._title_label)
        
        # 可编辑属性区域
        self._form_layout = QFormLayout()
        self._form_layout.setContentsMargins(2, 2, 2, 2)
        self._form_layout.setSpacing(6)
        
        # 包含所有属性的容器（方便动态更新）
        self._container = QWidget()
        self._container.setLayout(self._form_layout)
        main_layout.addWidget(self._container)
        
        # 默认情况下隐藏属性编辑区域
        self._container.setVisible(False)
        
        # 创建各种属性分组
        self._create_transform_group()
        self._create_geometry_group()
        self._create_material_group()
    
    def _create_transform_group(self):
        """创建变换属性组"""
        transform_group = QGroupBox("变换")
        transform_layout = QVBoxLayout(transform_group)
        
        # 位置控件
        position_layout = QFormLayout()
        self._position_x = self._create_double_spinbox("position_x")
        self._position_y = self._create_double_spinbox("position_y")
        self._position_z = self._create_double_spinbox("position_z")
        
        position_layout.addRow("X:", self._position_x)
        position_layout.addRow("Y:", self._position_y)
        position_layout.addRow("Z:", self._position_z)
        
        position_group = QGroupBox("位置")
        position_group.setLayout(position_layout)
        transform_layout.addWidget(position_group)
        
        # 旋转控件
        rotation_layout = QFormLayout()
        self._rotation_x = self._create_double_spinbox("rotation_x", -180, 180)
        self._rotation_y = self._create_double_spinbox("rotation_y", -180, 180)
        self._rotation_z = self._create_double_spinbox("rotation_z", -180, 180)
        
        rotation_layout.addRow("X:", self._rotation_x)
        rotation_layout.addRow("Y:", self._rotation_y)
        rotation_layout.addRow("Z:", self._rotation_z)
        
        rotation_group = QGroupBox("旋转")
        rotation_group.setLayout(rotation_layout)
        transform_layout.addWidget(rotation_group)
        
        # 缩放控件
        scale_layout = QFormLayout()
        self._scale_x = self._create_double_spinbox("scale_x", 0.01, 100.0, 0.1)
        self._scale_y = self._create_double_spinbox("scale_y", 0.01, 100.0, 0.1)
        self._scale_z = self._create_double_spinbox("scale_z", 0.01, 100.0, 0.1)
        
        scale_layout.addRow("X:", self._scale_x)
        scale_layout.addRow("Y:", self._scale_y)
        scale_layout.addRow("Z:", self._scale_z)
        
        scale_group = QGroupBox("缩放")
        scale_group.setLayout(scale_layout)
        transform_layout.addWidget(scale_group)
        
        self._form_layout.addRow(transform_group)
    
    def _create_geometry_group(self):
        """创建几何属性组"""
        geometry_group = QGroupBox("几何")
        geometry_layout = QFormLayout(geometry_group)
        
        # 几何类型选择
        self._geometry_type = QComboBox()
        for geo_type in GeometryType:
            self._geometry_type.addItem(geo_type.name, geo_type.value)
        self._geometry_type.currentIndexChanged.connect(
            lambda: self.propertyChanged.emit("type", self._geometry_type.currentData())
        )
        geometry_layout.addRow("类型:", self._geometry_type)
        
        # 名称
        self._name_edit = QLineEdit()
        self._name_edit.editingFinished.connect(
            lambda: self.propertyChanged.emit("name", self._name_edit.text())
        )
        geometry_layout.addRow("名称:", self._name_edit)
        
        # 可见性
        self._visibility = QCheckBox("可见")
        self._visibility.toggled.connect(
            lambda checked: self.propertyChanged.emit("visible", checked)
        )
        geometry_layout.addRow("", self._visibility)
        
        self._form_layout.addRow(geometry_group)
    
    def _create_material_group(self):
        """创建材质属性组"""
        material_group = QGroupBox("材质")
        material_layout = QFormLayout(material_group)
        
        # 颜色选择按钮
        color_button_layout = QHBoxLayout()
        self._color_preview = QLabel()
        self._color_preview.setFixedSize(24, 24)
        self._color_preview.setStyleSheet("background-color: #FF0000; border: 1px solid #888888;")
        
        self._color_button = QPushButton("选择")
        self._color_button.clicked.connect(self._show_color_dialog)
        
        color_button_layout.addWidget(self._color_preview)
        color_button_layout.addWidget(self._color_button)
        color_button_layout.addStretch()
        
        material_layout.addRow("颜色:", color_button_layout)
        
        # 透明度控件
        self._opacity = QDoubleSpinBox()
        self._opacity.setRange(0.0, 1.0)
        self._opacity.setSingleStep(0.1)
        self._opacity.setDecimals(2)
        self._opacity.valueChanged.connect(self._update_opacity)
        material_layout.addRow("透明度:", self._opacity)
        
        self._form_layout.addRow(material_group)
    
    def _create_double_spinbox(self, property_name, min_val=-1000.0, max_val=1000.0, step=1.0):
        """
        创建双精度数字输入框
        
        参数:
            property_name: 属性名称
            min_val: 最小值
            max_val: 最大值
            step: 步长
        """
        spinbox = QDoubleSpinBox()
        spinbox.setRange(min_val, max_val)
        spinbox.setSingleStep(step)
        spinbox.setDecimals(3)
        spinbox.valueChanged.connect(
            lambda value: self.propertyChanged.emit(property_name, value)
        )
        return spinbox
    
    def _show_color_dialog(self):
        """显示颜色选择对话框"""
        current_color = self._property_viewmodel.get_property("material_color")
        if current_color is None:
            current_color = QColor(255, 0, 0)
        else:
            # 将RGBA数组转换为QColor
            r, g, b, a = [int(c * 255) if i < 3 else c for i, c in enumerate(current_color)]
            current_color = QColor(r, g, b)
        
        color = QColorDialog.getColor(current_color, self, "选择颜色", QColorDialog.ShowAlphaChannel)
        
        if color.isValid():
            # 更新预览
            self._color_preview.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #888888;")
            
            # 发出颜色变更信号 (转换为RGBA格式，RGB为0-1，A为0-1)
            rgba = [color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0, color.alpha() / 255.0]
            self.propertyChanged.emit("material_color", rgba)
            
            # 更新透明度控件
            self._opacity.blockSignals(True)
            self._opacity.setValue(rgba[3])
            self._opacity.blockSignals(False)
    
    def _update_opacity(self, value):
        """
        更新透明度
        
        参数:
            value: 新的透明度值 (0.0-1.0)
        """
        current_color = self._property_viewmodel.get_property("material_color")
        if current_color is not None:
            # 创建新的颜色值，但只更新alpha通道
            new_color = current_color.copy()
            new_color[3] = value
            self.propertyChanged.emit("material_color", new_color)
    
    def _update_ui(self):
        """更新UI以反映当前选中对象的属性"""
        # 获取选中的对象
        selected_object = self._property_viewmodel.selected_object
        
        if selected_object is None:
            # 如果没有选中对象，隐藏属性编辑区域
            self._title_label.setText("未选择对象")
            self._container.setVisible(False)
            return
        
        # 显示属性编辑区域
        self._container.setVisible(True)
        
        # 更新标题
        name = self._property_viewmodel.get_property("name") or "未命名对象"
        self._title_label.setText(f"编辑: {name}")
        
        # 更新名称
        self._name_edit.blockSignals(True)
        self._name_edit.setText(name)
        self._name_edit.blockSignals(False)
        
        # 更新位置
        position = self._property_viewmodel.get_property("position")
        if position is not None:
            self._position_x.blockSignals(True)
            self._position_y.blockSignals(True)
            self._position_z.blockSignals(True)
            
            self._position_x.setValue(position[0])
            self._position_y.setValue(position[1])
            self._position_z.setValue(position[2])
            
            self._position_x.blockSignals(False)
            self._position_y.blockSignals(False)
            self._position_z.blockSignals(False)
        
        # 更新旋转
        rotation = self._property_viewmodel.get_property("rotation")
        if rotation is not None:
            self._rotation_x.blockSignals(True)
            self._rotation_y.blockSignals(True)
            self._rotation_z.blockSignals(True)
            
            self._rotation_x.setValue(rotation[0])
            self._rotation_y.setValue(rotation[1])
            self._rotation_z.setValue(rotation[2])
            
            self._rotation_x.blockSignals(False)
            self._rotation_y.blockSignals(False)
            self._rotation_z.blockSignals(False)
        
        # 更新缩放
        scale = self._property_viewmodel.get_property("scale")
        if scale is not None:
            self._scale_x.blockSignals(True)
            self._scale_y.blockSignals(True)
            self._scale_z.blockSignals(True)
            
            self._scale_x.setValue(scale[0])
            self._scale_y.setValue(scale[1])
            self._scale_z.setValue(scale[2])
            
            self._scale_x.blockSignals(False)
            self._scale_y.blockSignals(False)
            self._scale_z.blockSignals(False)
        
        # 更新几何类型
        geo_type = self._property_viewmodel.get_property("type")
        if geo_type is not None:
            self._geometry_type.blockSignals(True)
            index = self._geometry_type.findData(geo_type)
            self._geometry_type.setCurrentIndex(index if index >= 0 else 0)
            self._geometry_type.blockSignals(False)
        
        # 更新可见性
        visible = self._property_viewmodel.get_property("visible")
        if visible is not None:
            self._visibility.blockSignals(True)
            self._visibility.setChecked(visible)
            self._visibility.blockSignals(False)
        
        # 更新材质颜色
        color = self._property_viewmodel.get_property("material_color")
        if color is not None:
            # 更新颜色预览
            r, g, b = [int(c * 255) for c in color[:3]]
            preview_color = QColor(r, g, b)
            self._color_preview.setStyleSheet(f"background-color: {preview_color.name()}; border: 1px solid #888888;")
            
            # 更新透明度
            self._opacity.blockSignals(True)
            self._opacity.setValue(color[3])
            self._opacity.blockSignals(False) 