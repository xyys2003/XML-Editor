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
        
        # 设置初始宽度
        self.setMinimumWidth(200)
        
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
        
        # 尺寸控件 - 创建一个尺寸组
        self._size_group = QGroupBox("尺寸")
        self._size_layout = QFormLayout(self._size_group)
        
        # 创建适用于不同几何体类型的控件
        # 1. 通用三维尺寸控件 (用于box和ellipsoid)
        self._box_size_x = self._create_double_spinbox("scale_x", 0.01, 100.0, 0.1)
        self._box_size_y = self._create_double_spinbox("scale_y", 0.01, 100.0, 0.1)
        self._box_size_z = self._create_double_spinbox("scale_z", 0.01, 100.0, 0.1)
        
        # 2. 球体半径控件
        self._sphere_radius = self._create_double_spinbox("radius", 0.01, 100.0, 0.1)
        self._sphere_radius.valueChanged.connect(self._handle_sphere_radius_change)
        
        # 3. 圆柱体/胶囊体控件
        self._cylinder_radius = self._create_double_spinbox("cylinder_radius", 0.01, 100.0, 0.1)
        self._cylinder_length = self._create_double_spinbox("cylinder_length", 0.01, 100.0, 0.1)
        self._cylinder_radius.valueChanged.connect(self._handle_cylinder_radius_change)
        self._cylinder_length.valueChanged.connect(self._handle_cylinder_length_change)
        
        # 4. 椭球体半径控件
        self._ellipsoid_x = self._create_double_spinbox("scale_x", 0.01, 100.0, 0.1)
        self._ellipsoid_y = self._create_double_spinbox("scale_y", 0.01, 100.0, 0.1)
        self._ellipsoid_z = self._create_double_spinbox("scale_z", 0.01, 100.0, 0.1)
        
        # 将控件添加到布局，初始都不可见
        self._box_size_label_x = QLabel("X轴:")
        self._box_size_label_y = QLabel("Y轴:")
        self._box_size_label_z = QLabel("Z轴:")
        self._sphere_radius_label = QLabel("半径:")
        self._cylinder_radius_label = QLabel("半径:")
        self._cylinder_length_label = QLabel("长度:")
        self._ellipsoid_x_label = QLabel("X半径:")
        self._ellipsoid_y_label = QLabel("Y半径:")
        self._ellipsoid_z_label = QLabel("Z半径:")
        
        self._size_layout.addRow(self._box_size_label_x, self._box_size_x)
        self._size_layout.addRow(self._box_size_label_y, self._box_size_y)
        self._size_layout.addRow(self._box_size_label_z, self._box_size_z)
        self._size_layout.addRow(self._sphere_radius_label, self._sphere_radius)
        self._size_layout.addRow(self._cylinder_radius_label, self._cylinder_radius)
        self._size_layout.addRow(self._cylinder_length_label, self._cylinder_length)
        self._size_layout.addRow(self._ellipsoid_x_label, self._ellipsoid_x)
        self._size_layout.addRow(self._ellipsoid_y_label, self._ellipsoid_y)
        self._size_layout.addRow(self._ellipsoid_z_label, self._ellipsoid_z)
        
        # 隐藏所有尺寸控件
        self._hide_all_size_controls()
        
        transform_layout.addWidget(self._size_group)
        self._form_layout.addRow(transform_group)
        
        # 保留原来的缩放控件，但隐藏它们，用于兼容后端逻辑
        self._scale_x = self._create_double_spinbox("scale_x", 0.01, 100.0, 0.1)
        self._scale_y = self._create_double_spinbox("scale_y", 0.01, 100.0, 0.1)
        self._scale_z = self._create_double_spinbox("scale_z", 0.01, 100.0, 0.1)
        self._scale_x.hide()
        self._scale_y.hide()
        self._scale_z.hide()
    
    def _hide_all_size_controls(self):
        """隐藏所有尺寸控件"""
        # 立方体
        self._box_size_x.hide()
        self._box_size_y.hide()
        self._box_size_z.hide()
        self._box_size_label_x.hide()
        self._box_size_label_y.hide()
        self._box_size_label_z.hide()
        
        # 球体
        self._sphere_radius.hide()
        self._sphere_radius_label.hide()
        
        # 圆柱体/胶囊体
        self._cylinder_radius.hide()
        self._cylinder_length.hide()
        self._cylinder_radius_label.hide()
        self._cylinder_length_label.hide()
        
        # 椭球体
        self._ellipsoid_x.hide()
        self._ellipsoid_y.hide()
        self._ellipsoid_z.hide()
        self._ellipsoid_x_label.hide()
        self._ellipsoid_y_label.hide()
        self._ellipsoid_z_label.hide()
    
    def _show_size_controls_for_type(self, geo_type):
        """根据几何体类型显示相应的尺寸控件"""
        # 首先隐藏所有控件
        self._hide_all_size_controls()
        
        # 根据类型显示相应控件
        if geo_type == "box":
            self._box_size_x.show()
            self._box_size_y.show()
            self._box_size_z.show()
            self._box_size_label_x.show()
            self._box_size_label_y.show()
            self._box_size_label_z.show()
            self._size_group.setTitle("尺寸")
        elif geo_type == "sphere":
            self._sphere_radius.show()
            self._sphere_radius_label.show()
            self._size_group.setTitle("尺寸")
        elif geo_type in ["cylinder", "capsule"]:
            self._cylinder_radius.show()
            self._cylinder_length.show()
            self._cylinder_radius_label.show()
            self._cylinder_length_label.show()
            self._size_group.setTitle("尺寸")
        elif geo_type == "ellipsoid":
            self._ellipsoid_x.show()
            self._ellipsoid_y.show()
            self._ellipsoid_z.show()
            self._ellipsoid_x_label.show()
            self._ellipsoid_y_label.show()
            self._ellipsoid_z_label.show()
            self._size_group.setTitle("尺寸")
        elif geo_type == "plane":
            self._size_group.setTitle("尺寸 (不可调整)")
    
    def _handle_sphere_radius_change(self, value):
        """处理球体半径变化"""
        # 更新隐藏的缩放控件，保持一致性
        self._scale_x.blockSignals(True)
        self._scale_y.blockSignals(True)
        self._scale_z.blockSignals(True)
        
        self._scale_x.setValue(value)
        self._scale_y.setValue(value)
        self._scale_z.setValue(value)
        
        self._scale_x.blockSignals(False)
        self._scale_y.blockSignals(False)
        self._scale_z.blockSignals(False)
        
        # 发送统一的缩放值
        self.propertyChanged.emit("scale", [value, value, value])
    
    def _handle_cylinder_radius_change(self, value):
        """处理圆柱体/胶囊体半径变化"""
        length = self._cylinder_length.value()
        
        # 更新隐藏的缩放控件
        self._scale_x.blockSignals(True)
        self._scale_y.blockSignals(True)
        
        self._scale_x.setValue(value)
        self._scale_y.setValue(value)
        
        self._scale_x.blockSignals(False)
        self._scale_y.blockSignals(False)
        
        # 发送更新的缩放值
        self.propertyChanged.emit("scale", [value, value, length])
    
    def _handle_cylinder_length_change(self, value):
        """处理圆柱体/胶囊体长度变化"""
        radius = self._cylinder_radius.value()
        
        # 更新隐藏的Z轴缩放控件
        self._scale_z.blockSignals(True)
        self._scale_z.setValue(value)
        self._scale_z.blockSignals(False)
        
        # 发送更新的缩放值
        self.propertyChanged.emit("scale", [radius, radius, value])
    
    def _handle_sphere_scale(self, value):
        """原有的处理特殊几何体缩放联动"""
        # 保留此方法以兼容现有逻辑，但不再使用
        pass
    
    def _create_geometry_group(self):
        """创建几何属性组"""
        geometry_group = QGroupBox("几何")
        geometry_layout = QFormLayout(geometry_group)
        
        # 几何类型选择
        self._geometry_type = QComboBox()
        for geo_type in GeometryType:
            self._geometry_type.addItem(geo_type.name, geo_type.value)
        
        # 修改连接方式，增加处理逻辑
        self._geometry_type.currentIndexChanged.connect(self._on_geometry_type_changed)
        
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
    
    def _on_geometry_type_changed(self):
        """处理几何体类型变化"""
        # 获取新的几何体类型
        geo_type = self._geometry_type.currentData()
        
        # 发送类型变更信号
        self.propertyChanged.emit("type", geo_type)
        
        # 更新尺寸控件
        self._show_size_controls_for_type(geo_type)
        
        # 根据几何体类型设置默认尺寸
        scale = None
        
        if geo_type == "sphere":
            # 球体默认尺寸 - 统一半径
            radius = self._scale_x.value()  # 使用当前X值作为半径
            scale = [radius, radius, radius]
            
        elif geo_type in ["cylinder", "capsule"]:
            # 圆柱体/胶囊体默认尺寸 - 统一XY作为半径
            radius = self._scale_x.value()  # 使用当前X值作为半径
            length = self._scale_z.value()  # 使用当前Z值作为长度
            scale = [radius, radius, length]
        
        # 如果有默认尺寸，发送更新
        if scale:
            self.propertyChanged.emit("scale", scale)
    
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
        
        # 更新几何类型
        geo_type = self._property_viewmodel.get_property("type")
        if geo_type is not None:
            self._geometry_type.blockSignals(True)
            index = self._geometry_type.findData(geo_type)
            self._geometry_type.setCurrentIndex(index if index >= 0 else 0)
            self._geometry_type.blockSignals(False)
            
            # 根据几何体类型显示对应的尺寸控件
            self._show_size_controls_for_type(geo_type)
        
        # 更新缩放/尺寸值
        scale = self._property_viewmodel.get_property("scale")
        if scale is not None:
            # 同时更新隐藏的缩放控件
            self._scale_x.blockSignals(True)
            self._scale_y.blockSignals(True)
            self._scale_z.blockSignals(True)
            
            self._scale_x.setValue(scale[0])
            self._scale_y.setValue(scale[1])
            self._scale_z.setValue(scale[2])
            
            self._scale_x.blockSignals(False)
            self._scale_y.blockSignals(False)
            self._scale_z.blockSignals(False)
            
            # 根据几何体类型更新对应的尺寸控件
            if geo_type == "box":
                self._box_size_x.blockSignals(True)
                self._box_size_y.blockSignals(True)
                self._box_size_z.blockSignals(True)
                
                self._box_size_x.setValue(scale[0])
                self._box_size_y.setValue(scale[1])
                self._box_size_z.setValue(scale[2])
                
                self._box_size_x.blockSignals(False)
                self._box_size_y.blockSignals(False)
                self._box_size_z.blockSignals(False)
            
            elif geo_type == "sphere":
                self._sphere_radius.blockSignals(True)
                self._sphere_radius.setValue(scale[0])  # 使用X值作为半径
                self._sphere_radius.blockSignals(False)
            
            elif geo_type in ["cylinder", "capsule"]:
                self._cylinder_radius.blockSignals(True)
                self._cylinder_length.blockSignals(True)
                
                self._cylinder_radius.setValue(scale[0])  # 使用X值作为半径
                self._cylinder_length.setValue(scale[2])  # 使用Z值作为长度
                
                self._cylinder_radius.blockSignals(False)
                self._cylinder_length.blockSignals(False)
            
            elif geo_type == "ellipsoid":
                self._ellipsoid_x.blockSignals(True)
                self._ellipsoid_y.blockSignals(True)
                self._ellipsoid_z.blockSignals(True)
                
                self._ellipsoid_x.setValue(scale[0])
                self._ellipsoid_y.setValue(scale[1])
                self._ellipsoid_z.setValue(scale[2])
                
                self._ellipsoid_x.blockSignals(False)
                self._ellipsoid_y.blockSignals(False)
                self._ellipsoid_z.blockSignals(False)
        
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