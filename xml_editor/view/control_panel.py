"""
控制面板视图

提供场景操作控制，如创建对象、变换模式选择等。
"""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                          QGroupBox, QRadioButton, QComboBox, QLabel, 
                          QButtonGroup, QToolButton, QGridLayout, QFileDialog, QMessageBox,
                          QDialog, QListWidget, QListWidgetItem, QAbstractItemView, QApplication)
from PyQt5.QtCore import Qt, QMimeData, QSize
from PyQt5.QtGui import QDrag, QPixmap, QIcon
import os

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
        
        # 添加存档相关的按钮组
        save_group = QGroupBox("存档管理")
        save_layout = QVBoxLayout(save_group)
        
        # 自动存档按钮
        self.autoSaveButton = QPushButton("创建存档点")
        self.autoSaveButton.setToolTip("以时间戳创建存档")
        self.autoSaveButton.clicked.connect(self.auto_save_state)
        save_layout.addWidget(self.autoSaveButton)
        
        # 显示最近存档按钮
        self.showRecentSavesButton = QPushButton("查看存档")
        self.showRecentSavesButton.setToolTip("查看最近10个存档")
        self.showRecentSavesButton.clicked.connect(self.show_recent_saves)
        save_layout.addWidget(self.showRecentSavesButton)
        
        # 添加到主布局
        main_layout.addWidget(save_group)
        
        # 连接视图模型的信号
        self._control_viewmodel.saveStateCompleted.connect(self.on_save_completed)
        self._control_viewmodel.loadStateCompleted.connect(self.on_load_completed)
    
    def _create_operation_tools(self, parent_layout):
        """
        创建操作工具组
        
        参数:
            parent_layout: 父布局
        """
        operation_group = QGroupBox("操作模式")
        # 使用网格布局，3行2列（增加一行用于坐标系切换）
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
        
        # 创建坐标系切换按钮
        self._coord_sys_button = QPushButton("局部坐标系")
        self._coord_sys_button.setCheckable(True)  # 使按钮可以切换状态
        self._coord_sys_button.setChecked(True)    # 默认使用局部坐标系
        self._coord_sys_button.clicked.connect(self._on_coord_system_changed)
        operation_layout.addWidget(self._coord_sys_button, 2, 0, 1, 2)  # 按钮跨越两列
        
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
    
    def _on_coord_system_changed(self):
        """处理坐标系切换"""
        # 切换按钮状态
        use_local = self._coord_sys_button.isChecked()
        
        # 更新按钮文本和样式
        if use_local:
            self._coord_sys_button.setText("局部坐标系")
            self._coord_sys_button.setStyleSheet("background-color: #e0f0e0; color: #006000;")  # 绿色调
        else:
            self._coord_sys_button.setText("全局坐标系")
            self._coord_sys_button.setStyleSheet("background-color: #e0e0f0; color: #000060;")  # 蓝色调
        
        # 通知视图模型坐标系已更改
        self._control_viewmodel.use_local_coords = use_local 

    def save_state(self):
        """
        打开文件对话框并保存当前状态
        """
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存几何体存档", "", "JSON文件 (*.json)"
        )
        
        if file_path:
            self._control_viewmodel.save_state_to_json(file_path)

    def load_state(self):
        """
        打开文件对话框并加载状态
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "加载几何体存档", "", "JSON文件 (*.json)"
        )
        
        if file_path:
            self._control_viewmodel.load_state_from_json(file_path)

    def on_save_completed(self, file_path):
        """
        保存完成后的处理
        """
        QMessageBox.information(self, "保存成功", f"几何体存档已保存到:\n{file_path}")

    def on_load_completed(self, success):
        """
        加载完成后的处理
        """
        if success:
            QMessageBox.information(self, "加载成功", "几何体存档已成功加载")
        else:
            QMessageBox.warning(self, "加载失败", "无法加载几何体存档，请检查文件格式")

    def auto_save_state(self):
        """自动创建存档点"""
        try:
            file_path = self._control_viewmodel.auto_save_state()
            if file_path:
                QMessageBox.information(self, "存档成功", f"已创建存档:\n{os.path.basename(file_path)}")
            else:
                QMessageBox.warning(self, "存档失败", "创建存档失败，请查看控制台日志")
        except Exception as e:
            QMessageBox.critical(self, "存档错误", f"创建存档时发生错误：\n{str(e)}")
    
    def show_recent_saves(self):
        """显示最近存档对话框"""
        dialog = SavesDialog(self._control_viewmodel, self)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_save:
            # 加载选中的存档
            self._control_viewmodel.load_state_from_json(dialog.selected_save)


class SavesDialog(QDialog):
    """最近存档对话框"""
    
    def __init__(self, control_viewmodel, parent=None):
        super().__init__(parent)
        self.control_viewmodel = control_viewmodel
        self.selected_save = None
        
        self.setWindowTitle("最近存档")
        self.setMinimumSize(400, 300)
        
        self._init_ui()
        self._load_saves()
    
    def _init_ui(self):
        """初始化对话框UI"""
        layout = QVBoxLayout(self)
        
        # 创建列表控件
        self.savesList = QListWidget()
        self.savesList.setSelectionMode(QAbstractItemView.SingleSelection)
        self.savesList.setIconSize(QSize(24, 24))
        self.savesList.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.savesList)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 加载按钮
        self.loadButton = QPushButton("加载")
        self.loadButton.clicked.connect(self._on_load_clicked)
        button_layout.addWidget(self.loadButton)
        
        # 取消按钮
        self.cancelButton = QPushButton("取消")
        self.cancelButton.clicked.connect(self.reject)
        button_layout.addWidget(self.cancelButton)
        
        layout.addLayout(button_layout)
    
    def _load_saves(self):
        """加载最近的存档列表"""
        self.savesList.clear()
        
        # 获取最近10个存档
        recent_saves = self.control_viewmodel.get_recent_saves(10)
        
        if not recent_saves:
            # 如果没有存档，添加提示
            item = QListWidgetItem("没有找到存档")
            item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.savesList.addItem(item)
            return
        
        # 为每个存档创建列表项
        for save_path in recent_saves:
            save_info = self.control_viewmodel.get_save_info(save_path)
            
            # 创建列表项
            item_text = f"{save_info['name']}\n{save_info['time']}\n几何体数量: {save_info['geometry_count']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, save_path)
            
            self.savesList.addItem(item)
    
    def _on_item_double_clicked(self, item):
        """处理列表项双击事件"""
        save_path = item.data(Qt.UserRole)
        if save_path:
            self.selected_save = save_path
            self.accept()
    
    def _on_load_clicked(self):
        """处理加载按钮点击事件"""
        selected_items = self.savesList.selectedItems()
        if selected_items:
            save_path = selected_items[0].data(Qt.UserRole)
            if save_path:
                # 显示加载中提示
                QApplication.setOverrideCursor(Qt.WaitCursor)
                
                # 打印文件内容（用于调试）
                print(f"正在加载文件: {save_path}")
                self.control_viewmodel.print_save_content(save_path)
                
                # 加载文件
                success = self.control_viewmodel.load_state_from_json(save_path)
                
                # 恢复鼠标指针
                QApplication.restoreOverrideCursor()
                
                # 显示结果
                if success:
                    QMessageBox.information(self, "加载成功", "几何体存档已成功加载")
                    self.selected_save = save_path
                    self.accept()
                else:
                    QMessageBox.warning(self, "加载失败", 
                                        "无法加载几何体存档，请查看控制台日志")
            else:
                QMessageBox.warning(self, "无效文件", "选择的存档文件路径无效")
        else:
            QMessageBox.information(self, "提示", "请先选择一个存档") 