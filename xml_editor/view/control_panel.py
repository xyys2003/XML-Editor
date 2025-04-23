"""
控制面板视图

提供场景操作控制，如创建对象、变换模式选择等。
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QGroupBox, QRadioButton, QComboBox, QLabel, 
                           QButtonGroup, QToolButton, QGridLayout)
from PyQt5.QtCore import Qt

from ..model.geometry import TransformMode, OperationMode, GeometryType

class ControlPanel(QWidget):
    """
    控制面板视图类
    
    提供场景操作控制界面，包括几何体创建和变换模式选择等
    """
    
    def __init__(self, control_viewmodel, parent=None):
        """
        初始化控制面板
        
        参数:
            control_viewmodel: 控制视图模型的引用
            parent: 父窗口部件
        """
        super().__init__(parent)
        self._control_viewmodel = control_viewmodel
        
        # 连接视图模型的信号
        self._control_viewmodel.operationModeChanged.connect(self._update_operation_buttons)
        
        # 创建UI
        self._init_ui()
    
    def _init_ui(self):
        """初始化用户界面"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(8)
        
        # 创建操作模式组
        self._create_operation_tools(main_layout)
        
        # 创建几何体创建组
        self._create_geometry_tools(main_layout)
        
        # 底部填充空间
        main_layout.addStretch()
    
    def _create_operation_tools(self, parent_layout):
        """
        创建操作工具组
        
        参数:
            parent_layout: 父布局
        """
        operation_group = QGroupBox("操作模式")
        # 使用网格布局，2行2列
        operation_layout = QGridLayout(operation_group)
        operation_layout.setContentsMargins(4, 4, 4, 4)
        operation_layout.setSpacing(4)
        
        # 创建操作模式单选按钮
        self._translate_radio = QRadioButton("平移")
        self._rotate_radio = QRadioButton("旋转")
        self._scale_radio = QRadioButton("缩放")
        self._select_radio = QRadioButton("选择")
        
        # 添加按钮到网格布局，2行2列排列
        operation_layout.addWidget(self._translate_radio, 0, 0)
        operation_layout.addWidget(self._rotate_radio, 0, 1)
        operation_layout.addWidget(self._scale_radio, 1, 0)
        operation_layout.addWidget(self._select_radio, 1, 1)
        
        # 创建按钮组
        self._operation_button_group = QButtonGroup(self)
        self._operation_button_group.addButton(self._translate_radio, OperationMode.TRANSLATE.value)
        self._operation_button_group.addButton(self._rotate_radio, OperationMode.ROTATE.value)
        self._operation_button_group.addButton(self._scale_radio, OperationMode.SCALE.value)
        self._operation_button_group.addButton(self._select_radio, OperationMode.SELECT.value)
        self._operation_button_group.buttonClicked.connect(self._on_operation_mode_changed)
        
        # 默认选中平移模式
        self._translate_radio.setChecked(True)
        
        parent_layout.addWidget(operation_group)
    
    def _create_geometry_tools(self, parent_layout):
        """
        创建几何体工具组
        
        参数:
            parent_layout: 父布局
        """
        geometry_group = QGroupBox("创建几何体")
        geometry_layout = QVBoxLayout(geometry_group)
        geometry_layout.setContentsMargins(4, 4, 4, 4)
        geometry_layout.setSpacing(6)
        
        # 几何体类型选择
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("类型:"))
        
        self._geometry_type = QComboBox()
        for geo_type in GeometryType:
            self._geometry_type.addItem(geo_type.name, geo_type.value)
        
        type_layout.addWidget(self._geometry_type)
        geometry_layout.addLayout(type_layout)
        
        # 创建按钮
        create_button = QPushButton("创建")
        create_button.clicked.connect(self._on_create_geometry)
        geometry_layout.addWidget(create_button)
        
        parent_layout.addWidget(geometry_group)
    
    def _create_mode_button(self, text, icon_name=None):
        """
        创建模式按钮
        
        参数:
            text: 按钮文本
            icon_name: 图标名称（可选）
            
        返回:
            创建的按钮
        """
        button = QToolButton()
        button.setText(text)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        
        # 如果有图标，设置图标
        if icon_name:
            # 这里假设有一个图标资源，实际项目中需要替换为实际的图标路径
            # button.setIcon(QIcon(f":/icons/{icon_name}.png"))
            pass
        
        return button
    
    def _on_operation_mode_changed(self, button):
        """
        处理操作模式变更
        
        参数:
            button: 被点击的按钮
        """
        mode_id = self._operation_button_group.id(button)
        operation_mode = OperationMode(mode_id)
        
        # 更新视图模型的操作模式
        self._control_viewmodel.operation_mode = operation_mode
        
        # 根据操作模式同时更新变换模式
        if operation_mode == OperationMode.TRANSLATE:
            self._control_viewmodel.transform_mode = TransformMode.TRANSLATE
        elif operation_mode == OperationMode.ROTATE:
            self._control_viewmodel.transform_mode = TransformMode.ROTATE
        elif operation_mode == OperationMode.SCALE:
            self._control_viewmodel.transform_mode = TransformMode.SCALE
    
    def _on_create_geometry(self):
        """处理几何体创建请求"""
        # 获取选中的几何体类型
        type_value = self._geometry_type.currentData()
        geometry_type = GeometryType(type_value)
        
        # 调用视图模型创建几何体
        self._control_viewmodel._scene_viewmodel.create_geometry(geometry_type)
    
    def _update_operation_buttons(self, operation_mode):
        """
        更新操作按钮状态
        
        参数:
            operation_mode: 当前操作模式
        """
        self._operation_button_group.blockSignals(True)
        
        # 更新按钮选中状态
        if operation_mode == OperationMode.TRANSLATE:
            self._translate_radio.setChecked(True)
        elif operation_mode == OperationMode.ROTATE:
            self._rotate_radio.setChecked(True)
        elif operation_mode == OperationMode.SCALE:
            self._scale_radio.setChecked(True)
        elif operation_mode == OperationMode.SELECT:
            self._select_radio.setChecked(True)
        
        self._operation_button_group.blockSignals(False) 