"""
控制面板视图

提供场景操作控制，如创建对象、变换模式选择等。
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                          QGroupBox, QRadioButton, QComboBox, QLabel, 
                          QButtonGroup, QToolButton, QGridLayout)
from PyQt5.QtCore import Qt, QMimeData
from PyQt5.QtGui import QDrag, QPixmap

from ..model.geometry import OperationMode, GeometryType

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
        
        # 打印枚举值信息
        print("有效的几何体类型：")
        for geo_type in GeometryType:
            print(f"  {geo_type.name}: {geo_type.value}")
    
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
        self._observe_radio = QRadioButton("观察")
        self._translate_radio = QRadioButton("平移")
        self._rotate_radio = QRadioButton("旋转")
        self._scale_radio = QRadioButton("缩放")
        
        # 添加按钮到网格布局，2行2列排列
        operation_layout.addWidget(self._observe_radio, 0, 0)
        operation_layout.addWidget(self._translate_radio, 0, 1)
        operation_layout.addWidget(self._rotate_radio, 1, 0)
        operation_layout.addWidget(self._scale_radio, 1, 1)
        
        # 创建按钮组
        self._operation_button_group = QButtonGroup(self)
        self._operation_button_group.addButton(self._observe_radio, OperationMode.OBSERVE.value)
        self._operation_button_group.addButton(self._translate_radio, OperationMode.TRANSLATE.value)
        self._operation_button_group.addButton(self._rotate_radio, OperationMode.ROTATE.value)
        self._operation_button_group.addButton(self._scale_radio, OperationMode.SCALE.value)
        self._operation_button_group.buttonClicked.connect(self._on_operation_mode_changed)
        
        # 默认选中平移模式
        self._observe_radio.setChecked(True)
        
        parent_layout.addWidget(operation_group)
    
    def _create_geometry_tools(self, parent_layout):
        """
        创建几何体工具组
        
        参数:
            parent_layout: 父布局
        """
        geometry_group = QGroupBox("创建几何体")
        geometry_layout = QGridLayout(geometry_group)
        geometry_layout.setContentsMargins(4, 4, 4, 4)
        geometry_layout.setSpacing(6)
        
        # 使用枚举的字符串值 - 第一行
        self._create_box_button = self._create_draggable_button("立方体", GeometryType.BOX.value, geometry_layout, 0, 0)
        self._create_sphere_button = self._create_draggable_button("球体", GeometryType.SPHERE.value, geometry_layout, 0, 1)
        
        # 第二行
        self._create_cylinder_button = self._create_draggable_button("圆柱", GeometryType.CYLINDER.value, geometry_layout, 1, 0)
        self._create_plane_button = self._create_draggable_button("平面", GeometryType.PLANE.value, geometry_layout, 1, 1)
        
        # 第三行 - 添加胶囊体和椭球体按钮
        self._create_capsule_button = self._create_draggable_button("胶囊体", GeometryType.CAPSULE.value, geometry_layout, 2, 0)
        self._create_ellipsoid_button = self._create_draggable_button("椭球体", GeometryType.ELLIPSOID.value, geometry_layout, 2, 1)
        
        # 添加提示标签
        hint_label = QLabel("提示：拖拽几何体到场景中创建")
        hint_label.setAlignment(Qt.AlignCenter)
        geometry_layout.addWidget(hint_label, 3, 0, 1, 2)
        
        parent_layout.addWidget(geometry_group)
    
    def _create_draggable_button(self, text, geo_type_value, layout, row, col):
        """
        创建可拖拽的几何体按钮
        
        参数:
            text: 按钮文本
            geo_type_value: 几何体类型值
            layout: 父布局
            row: 行位置
            col: 列位置
            
        返回:
            创建的按钮
        """
        button = QPushButton(text)
        button.setProperty("geo_type", geo_type_value)
        print(f"创建按钮 '{text}' 的几何体类型: '{geo_type_value}'，类型: {type(geo_type_value)}")
        layout.addWidget(button, row, col)
        
        # 启用鼠标跟踪以实现拖拽
        button.mousePressEvent = lambda event, btn=button: self._start_drag(event, btn)
        
        return button
    
    def _start_drag(self, event, button):
        """
        开始拖拽操作
        
        参数:
            event: 鼠标事件
            button: 触发拖拽的按钮
        """
        if event.button() == Qt.LeftButton:
            # 获取几何体类型值
            geo_type_value = button.property("geo_type")
            
            # 创建拖拽对象
            drag = QDrag(button)
            mime_data = QMimeData()
            
            # 存储几何体类型值（无需转换为字符串形式）
            mime_data.setText(geo_type_value)
            drag.setMimeData(mime_data)
            
            # 创建拖拽预览图像
            pixmap = QPixmap(button.size())
            button.render(pixmap)
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            
            # 执行拖拽操作
            drag.exec_(Qt.CopyAction)
    
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
    
    def _update_operation_buttons(self, operation_mode):
        """
        更新操作按钮状态
        
        参数:
            operation_mode: 当前操作模式
        """
        self._operation_button_group.blockSignals(True)
        
        # 更新按钮选中状态
        if operation_mode == OperationMode.OBSERVE:
            self._observe_radio.setChecked(True)
        elif operation_mode == OperationMode.TRANSLATE:
            self._translate_radio.setChecked(True)
        elif operation_mode == OperationMode.ROTATE:
            self._rotate_radio.setChecked(True)
        elif operation_mode == OperationMode.SCALE:
            self._scale_radio.setChecked(True)
        
        self._operation_button_group.blockSignals(False) 