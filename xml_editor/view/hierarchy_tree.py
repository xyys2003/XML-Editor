"""
层级树视图

显示场景中对象的层级结构，允许用户选择和管理对象。
"""

from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu, QApplication, QAction, QToolBar, QPushButton, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QKeySequence, QIcon
import copy
from ..model.geometry import GeometryType

class HierarchyTree(QTreeWidget):
    """
    层级树视图类
    
    显示场景中对象的层级结构，并处理对象的选择和右键菜单
    """
    
    def __init__(self, hierarchy_viewmodel, parent=None):
        """
        初始化层级树视图
        
        参数:
            hierarchy_viewmodel: 层级视图模型的引用
            parent: 父窗口部件
        """
        super().__init__(parent)
        self._hierarchy_viewmodel = hierarchy_viewmodel
        
        # 设置树视图的属性
        self.setHeaderLabel("对象")
        self.setSelectionMode(QTreeWidget.ExtendedSelection)  # 允许多选
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.InternalMove)
        
        # 内部状态
        self._ctrl_pressed = False
        self._multi_selected_items = []  # 多选项列表
        
        # 连接信号
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # 禁用内部拖放处理，我们将手动处理
        self.setDefaultDropAction(Qt.IgnoreAction)
        
        # 连接视图模型的信号
        self._hierarchy_viewmodel.hierarchyChanged.connect(self._update_tree)
        self._hierarchy_viewmodel.selectionChanged.connect(self._update_selection_from_viewmodel)
        
        # 初始化树
        self._update_tree()
        
        # 创建刷新计时器，用于延迟双重刷新
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._force_refresh)

    def create_refresh_button(self):
        """创建一个刷新按钮，可以添加到工具栏或面板中"""
        refresh_button = QPushButton("刷新层级视图")
        refresh_button.clicked.connect(self.refresh_tree)
        return refresh_button
    
    def refresh_tree(self):
        """手动刷新树视图"""
        # 保存当前选中状态
        selected_geometries = self._hierarchy_viewmodel.selected_geometries
        
        # 强制触发场景和层级更新信号
        self._hierarchy_viewmodel._scene_viewmodel.geometriesChanged.emit()
        self._hierarchy_viewmodel.hierarchyChanged.emit()
        
        # 强制更新树
        self._update_tree()
        
        # 恢复选择
        if selected_geometries:
            self._hierarchy_viewmodel.select_geometries(selected_geometries)
        
        # 强制重绘
        self.update()
        
        # 显示状态信息
        print("手动刷新完成")
    
    def _force_refresh(self):
        """强制刷新树视图和相关视图"""
        # 触发场景更新信号
        self._hierarchy_viewmodel._scene_viewmodel.geometriesChanged.emit()
        
        # 强制重绘
        self.update()
        QApplication.processEvents()  # 立即处理事件队列中的绘制事件

    def keyPressEvent(self, event):
        """处理按键按下事件"""
        # 记录Ctrl键状态
        if event.key() == Qt.Key_Control:
            self._ctrl_pressed = True
        super().keyPressEvent(event)
    
    def keyReleaseEvent(self, event):
        """处理按键释放事件"""
        # 记录Ctrl键状态
        if event.key() == Qt.Key_Control:
            self._ctrl_pressed = False
        super().keyReleaseEvent(event)
    
    def mousePressEvent(self, event):
        """处理鼠标按下事件"""
        item = self.itemAt(event.pos())
        
        # 左键点击
        if event.button() == Qt.LeftButton:
            # 按住Ctrl键进行多选
            if self._ctrl_pressed and item:
                geometry = self._get_geometry_from_item(item)
                if geometry:
                    # 切换选择状态
                    self._hierarchy_viewmodel.toggle_geometry_selection(geometry)
                event.accept()
                return
            elif not self._ctrl_pressed:
                # 非Ctrl点击，清空多选
                if item:
                    geometry = self._get_geometry_from_item(item)
                    if geometry:
                        self._hierarchy_viewmodel.select_geometry(geometry)
                else:
                    self._hierarchy_viewmodel.clear_selection()
        
        # 调用父类方法处理其他情况
        super().mousePressEvent(event)
    
    def _get_geometry_from_item(self, item):
        """根据树项获取对应的几何体"""
        if not item:
            return None
            
        geometry_id = item.data(0, Qt.UserRole)
        
        # 查找对应的几何体
        for geometry in self._find_all_geometries(self._hierarchy_viewmodel.geometries):
            if id(geometry) == geometry_id:
                return geometry
                
        return None
    
    def _update_selection_from_viewmodel(self, selected_geometries):
        """根据视图模型更新树的选择状态"""
        # 阻断反馈循环
        self.blockSignals(True)
        
        # 清除当前所有选择
        self.clearSelection()
        self._multi_selected_items.clear()
        
        # 选择新的项目
        for geometry in selected_geometries:
            self._select_geometry_by_id(id(geometry), add_to_selection=True)
        
        self.blockSignals(False)
    
    def _on_selection_changed(self):
        """处理选择变化事件"""
        if not self._ctrl_pressed:
            # 单选模式，不由这里处理
            pass
    
    def _update_tree(self):
        """更新树视图以反映当前场景结构"""
        # 获取当前选中的几何体ID列表
        selected_ids = [id(geo) for geo in self._hierarchy_viewmodel.selected_geometries]
        
        # 清空树
        self.clear()
        
        # 添加所有几何体到树
        for geometry in self._hierarchy_viewmodel.geometries:
            self._add_geometry_to_tree(geometry)
        
        # 恢复选择状态
        for geo_id in selected_ids:
            self._select_geometry_by_id(geo_id, add_to_selection=True)
    
    def _add_geometry_to_tree(self, geometry, parent_item=None):
        """
        将几何体添加到树中
        
        参数:
            geometry: 要添加的几何体
            parent_item: 父树项（如果有）
        
        返回:
            新创建的树项
        """
        # 创建树项
        item = QTreeWidgetItem()
        item.setText(0, geometry.name)
        item.setData(0, Qt.UserRole, id(geometry))
        
        # 添加到树
        if parent_item is None:
            self.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        
        # 递归添加子对象
        if hasattr(geometry, 'children') and geometry.children:
            for child in geometry.children:
                self._add_geometry_to_tree(child, item)
        
        return item
    
    def _find_all_geometries(self, geometries):
        """
        递归查找场景中的所有几何体
        
        参数:
            geometries: 几何体列表
            
        返回:
            所有几何体的列表（包括子对象）
        """
        result = []
        for geometry in geometries:
            result.append(geometry)
            if hasattr(geometry, 'children') and geometry.children:
                result.extend(self._find_all_geometries(geometry.children))
        return result
    
    def _show_context_menu(self, position):
        """
        显示右键菜单
        
        参数:
            position: 菜单位置
        """
        # 获取点击位置的项
        clicked_item = self.itemAt(position)
        
        # 获取当前选中的几何体
        selected_geometries = self._hierarchy_viewmodel.selected_geometries
        
        # 如果点击了非选中项，更改选择
        if clicked_item and self._get_geometry_from_item(clicked_item) not in selected_geometries:
            # 如果按下Ctrl键，添加到选择
            if self._ctrl_pressed:
                geometry = self._get_geometry_from_item(clicked_item)
                if geometry:
                    self._hierarchy_viewmodel.toggle_geometry_selection(geometry)
            else:
                # 否则，替换选择
                geometry = self._get_geometry_from_item(clicked_item)
                if geometry:
                    self._hierarchy_viewmodel.select_geometry(geometry)
        
        # 重新获取选中的几何体
        selected_geometries = self._hierarchy_viewmodel.selected_geometries
        
        # 创建上下文菜单
        menu = QMenu(self)
        
        # 点击空白处的菜单
        if clicked_item is None:
            # 创建菜单
            create_menu = menu.addMenu("新建")
            create_group_action = create_menu.addAction("组")
            create_box_action = create_menu.addAction("立方体")
            create_sphere_action = create_menu.addAction("球体")
            create_cylinder_action = create_menu.addAction("圆柱体")
            create_capsule_action = create_menu.addAction("胶囊体")
            create_plane_action = create_menu.addAction("平面")
            create_ellipsoid_action = create_menu.addAction("椭球体")
            
            # 粘贴功能
            paste_action = menu.addAction("粘贴")
            paste_action.setEnabled(self._hierarchy_viewmodel.has_clipboard_content)
        else:
            # 点击项目的菜单
            # 确定点击的几何体
            clicked_geometry = self._get_geometry_from_item(clicked_item)
            
            # 多选状态下的菜单
            if len(selected_geometries) > 1:
                # 多选通用菜单项
                delete_action = menu.addAction("删除选中项")
                copy_action = menu.addAction("复制选中项")
                menu.addSeparator()
                group_action = menu.addAction("组合到新组")
                
                # 如果点击的是组，添加粘贴到组选项
                if clicked_geometry and clicked_geometry.type == 'group':
                    menu.addSeparator()
                    paste_action = menu.addAction("粘贴到这个组")
                    paste_action.setEnabled(self._hierarchy_viewmodel.has_clipboard_content)
            else:
                # 单选状态下的菜单
                # 如果是组，显示创建子项菜单
                if clicked_geometry and clicked_geometry.type == 'group':
                    create_menu = menu.addMenu("新建子对象")
                    create_group_action = create_menu.addAction("组")
                    create_box_action = create_menu.addAction("立方体")
                    create_sphere_action = create_menu.addAction("球体")
                    create_cylinder_action = create_menu.addAction("圆柱体")
                    create_capsule_action = create_menu.addAction("胶囊体")
                    create_plane_action = create_menu.addAction("平面")
                    create_ellipsoid_action = create_menu.addAction("椭球体")
                    menu.addSeparator()
                    
                    # 粘贴功能
                    paste_action = menu.addAction("粘贴")
                    paste_action.setEnabled(self._hierarchy_viewmodel.has_clipboard_content)
                else:
                    create_menu = None
                
                # 通用操作
                rename_action = menu.addAction("重命名")
                delete_action = menu.addAction("删除")
                menu.addSeparator()
                copy_action = menu.addAction("复制")
        
        # 显示菜单并获取选择的操作
        action = menu.exec_(self.mapToGlobal(position))
        
        # 如果用户没有选择任何操作，直接返回
        if not action:
            return
        
        # 处理多选操作
        if len(selected_geometries) > 1:
            if action == delete_action:
                self._hierarchy_viewmodel.remove_selected_geometries()
                return
            elif action == copy_action:
                self._hierarchy_viewmodel.copy_selected_geometries()
                return
            elif action == group_action:
                new_group = self._hierarchy_viewmodel.group_selected_geometries()
                if new_group:
                    # 选择新组
                    self._hierarchy_viewmodel.select_geometry(new_group)
                return
            elif 'paste_action' in locals() and action == paste_action:
                # 确定目标父节点
                parent_geometry = clicked_geometry if clicked_geometry.type == 'group' else None
                if parent_geometry:
                    self._hierarchy_viewmodel.paste_geometries(parent_geometry)
                return
        
        # 处理创建操作
        parent_geometry = None
        if clicked_item:
            parent_geometry = self._get_geometry_from_item(clicked_item)
            # 如果父节点不是组，则不能作为父节点
            if parent_geometry and parent_geometry.type != 'group':
                parent_geometry = None
        
        # 处理各种创建动作
        if 'create_menu' in locals() and create_menu:
            geo_type_map = {
                create_box_action: GeometryType.BOX,
                create_sphere_action: GeometryType.SPHERE,
                create_cylinder_action: GeometryType.CYLINDER,
                create_capsule_action: GeometryType.CAPSULE,
                create_plane_action: GeometryType.PLANE,
                create_ellipsoid_action: GeometryType.ELLIPSOID
            }
            
            if action == create_group_action:
                # 创建组
                new_group = self._hierarchy_viewmodel.create_group(parent=parent_geometry)
                if new_group:
                    self._hierarchy_viewmodel.select_geometry(new_group)
            elif action in geo_type_map:
                # 创建几何体
                geo_type = geo_type_map[action]
                new_geo = self._hierarchy_viewmodel._scene_viewmodel.create_geometry(
                    geo_type=geo_type, parent=parent_geometry)
                if new_geo:
                    self._hierarchy_viewmodel.select_geometry(new_geo)
        
        # 处理粘贴操作
        if 'paste_action' in locals() and action == paste_action:
            self._hierarchy_viewmodel.paste_geometries(parent_geometry)
            return
        
        # 处理单项操作
        if clicked_item and len(selected_geometries) <= 1:
            if action == rename_action:
                self.editItem(clicked_item)
            elif action == delete_action:
                geometry = self._get_geometry_from_item(clicked_item)
                if geometry:
                    self._hierarchy_viewmodel.remove_geometry(geometry)
            elif action == copy_action:
                geometry = self._get_geometry_from_item(clicked_item)
                if geometry:
                    self._hierarchy_viewmodel.copy_geometry(geometry)
    
    def _select_geometry_by_id(self, geometry_id, add_to_selection=False):
        """根据几何体ID在树中选择对应项"""
        if not add_to_selection:
            self.clearSelection()
            self._multi_selected_items.clear()
        
        # 在所有顶层项中查找
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            # 检查当前项
            if item.data(0, Qt.UserRole) == geometry_id:
                item.setSelected(True)
                if add_to_selection:
                    self._multi_selected_items.append(item)
                return True
            # 递归检查子项
            if self._select_geometry_in_children(item, geometry_id, add_to_selection):
                return True
        
        return False
    
    def _select_geometry_in_children(self, parent_item, geometry_id, add_to_selection):
        """在父项的子项中递归查找并选择几何体"""
        for i in range(parent_item.childCount()):
            child_item = parent_item.child(i)
            # 检查当前子项
            if child_item.data(0, Qt.UserRole) == geometry_id:
                child_item.setSelected(True)
                if add_to_selection:
                    self._multi_selected_items.append(child_item)
                return True
            # 递归检查其子项
            if self._select_geometry_in_children(child_item, geometry_id, add_to_selection):
                return True
        
        return False

    def dragEnterEvent(self, event):
        """处理拖拽进入事件"""
        if event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        """处理拖拽移动事件"""
        if event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        """处理拖放事件，支持多选拖拽"""
        if event.source() != self:
            super().dropEvent(event)
            return
        
        # 获取拖放位置的项
        drop_item = self.itemAt(event.pos())
        
        # 获取被拖拽的项（可能是多个）
        dragged_items = self.selectedItems()
        if not dragged_items:
            event.ignore()
            return
        
        # 获取对应的几何体对象
        dragged_geometries = []
        for item in dragged_items:
            geometry = self._get_geometry_from_item(item)
            if geometry:
                dragged_geometries.append(geometry)
        
        if not dragged_geometries:
            event.ignore()
            return
        
        # 获取目标几何体
        drop_geometry = self._get_geometry_from_item(drop_item) if drop_item else None
        
        # 检查是否有无效的拖放
        for dragged_item in dragged_items:
            if drop_item == dragged_item or self._is_ancestor_of(dragged_item, drop_item):
                event.ignore()
                return
        
        operation_success = False
        
        # 如果拖放到组上，则所有选中项都成为该组的子项
        if drop_geometry and drop_geometry.type == 'group':
            # 确保目标组不在被拖拽的几何体中
            if drop_geometry not in dragged_geometries:
                # 将所有拖拽的几何体设置为组的子项
                success_count = 0
                for geometry in dragged_geometries:
                    if self._hierarchy_viewmodel.reparent_geometry(geometry, drop_geometry):
                        success_count += 1
                
                operation_success = (success_count > 0)
        
        # 如果拖放到非组几何体上，则创建新组并将所有几何体（包括目标）放入该组中
        elif drop_geometry and drop_geometry.type != 'group':
            # 确保目标几何体不在被拖拽的几何体中
            if drop_geometry not in dragged_geometries:
                # 创建一个包含所有几何体的组
                all_geometries = [drop_geometry] + dragged_geometries
                new_group = self._hierarchy_viewmodel.group_geometries(
                    all_geometries, name="New Group", parent=drop_geometry.parent)
                operation_success = (new_group is not None)
        
        # 如果拖放到空白区域，则所有选中项都移动到顶层
        elif not drop_item:
            # 将所有拖拽的几何体移动到顶层
            success_count = 0
            for geometry in dragged_geometries:
                if self._hierarchy_viewmodel.reparent_geometry(geometry, None):
                    success_count += 1
            
            operation_success = (success_count > 0)
        
        # 确保操作完成后触发信号
        if operation_success:
            # 立即触发更新
            self._hierarchy_viewmodel._scene_viewmodel.geometriesChanged.emit()
            
            # 确保被操作的几何体仍然保持选中状态
            self._hierarchy_viewmodel.select_geometries(dragged_geometries)
            
            # 安排延迟刷新，解决更新滞后问题
            self._refresh_timer.start(100)  # 100毫秒后再次刷新
            
            event.accept()
        else:
            event.ignore()

    def _is_ancestor_of(self, potential_ancestor, item):
        """检查一个项是否是另一个项的祖先"""
        if not item:
            return False
        
        parent = item.parent()
        while parent:
            if parent == potential_ancestor:
                return True
            parent = parent.parent()
        
        return False

    def mouseMoveEvent(self, event):
        """处理鼠标移动事件，支持开始拖放"""
        # 只有在非多选模式下才允许拖放
        if not self._ctrl_pressed:
            super().mouseMoveEvent(event)
        else:
            # 在多选模式下阻止拖放
            event.ignore() 