"""
层级树视图

显示场景中对象的层级结构，允许用户选择和管理对象。
"""

from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu
from PyQt5.QtCore import Qt, pyqtSignal
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
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.InternalMove)
        
        # 连接信号
        self.itemClicked.connect(self._on_item_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        
        # 连接视图模型的信号
        self._hierarchy_viewmodel.hierarchyChanged.connect(self._update_tree)
        
        # 初始化树
        self._update_tree()
    
    def _update_tree(self):
        """更新树视图以反映当前场景结构"""
        # 保存当前选中项
        current_selection = self.selectedItems()
        current_id = None
        if current_selection:
            current_id = current_selection[0].data(0, Qt.UserRole)
        
        # 清空树
        self.clear()
        
        # 添加所有几何体到树
        for geometry in self._hierarchy_viewmodel.geometries:
            self._add_geometry_to_tree(geometry)
        
        # 恢复之前的选择
        if current_id is not None:
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                if item.data(0, Qt.UserRole) == current_id:
                    self.setCurrentItem(item)
                    break
    
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
    
    def _on_item_clicked(self, item, column):
        """
        处理树项点击事件
        
        参数:
            item: 被点击的树项
            column: 被点击的列
        """
        geometry_id = item.data(0, Qt.UserRole)
        
        # 查找点击的几何体
        for geometry in self._find_all_geometries(self._hierarchy_viewmodel.geometries):
            if id(geometry) == geometry_id:
                self._hierarchy_viewmodel.select_geometry(geometry)
                break
    
    def _on_selection_changed(self):
        """处理选择变化事件"""
        selected_items = self.selectedItems()
        if selected_items:
            self._on_item_clicked(selected_items[0], 0)
    
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
        item = self.itemAt(position)
        
        # 创建上下文菜单
        menu = QMenu(self)
        
        if item is None:
            # 在空白处右键显示创建菜单
            create_menu = menu.addMenu("新建")
            # 添加创建组选项
            create_group_action = create_menu.addAction("组")
            # 添加创建几何体选项
            create_box_action = create_menu.addAction("立方体")
            create_sphere_action = create_menu.addAction("球体")
            create_cylinder_action = create_menu.addAction("圆柱体")
        else:
            # 获取选中项对应的几何体
            geometry_id = item.data(0, Qt.UserRole)
            selected_geometry = None
            for geometry in self._find_all_geometries(self._hierarchy_viewmodel.geometries):
                if id(geometry) == geometry_id:
                    selected_geometry = geometry
                    break
            
            # 只有组对象才显示"新建子对象"菜单
            if selected_geometry and hasattr(selected_geometry, 'type') and selected_geometry.type == 'group':
                create_menu = menu.addMenu("新建子对象")
                create_group_action = create_menu.addAction("组")
                create_box_action = create_menu.addAction("立方体")
                create_sphere_action = create_menu.addAction("球体")
                create_cylinder_action = create_menu.addAction("圆柱体")
                menu.addSeparator()
            else:
                # 如果不是组对象，则不创建"新建子对象"菜单
                create_menu = None
                create_group_action = None
                create_box_action = None
                create_sphere_action = None
                create_cylinder_action = None
            
            # 通用的操作菜单
            rename_action = menu.addAction("重命名")
            delete_action = menu.addAction("删除")
            menu.addSeparator()
            copy_action = menu.addAction("复制")
        
        # 显示菜单并处理结果
        action = menu.exec_(self.mapToGlobal(position))
        
        # 如果用户没有选择任何操作，直接返回
        if not action:
            return
        
        # 处理创建操作
        parent_geometry = None
        if item is not None:
            # 获取选中项对应的几何体作为父节点
            geometry_id = item.data(0, Qt.UserRole)
            for geometry in self._find_all_geometries(self._hierarchy_viewmodel.geometries):
                if id(geometry) == geometry_id:
                    parent_geometry = geometry
                    break
        
        # 如果父节点不是组，则不能添加子对象
        if parent_geometry and hasattr(parent_geometry, 'type') and parent_geometry.type != 'group':
            parent_geometry = None
        
        # 处理各种创建动作
        new_object = None
        if create_menu and action in (create_group_action, create_box_action, create_sphere_action, create_cylinder_action):
            if action == create_group_action:
                # 创建新组
                new_object = self._hierarchy_viewmodel.create_group(parent=parent_geometry)
            elif action == create_box_action:
                # 创建立方体
                new_object = self._hierarchy_viewmodel._scene_viewmodel.create_geometry(
                    geo_type=GeometryType.BOX, parent=parent_geometry)
            elif action == create_sphere_action:
                # 创建球体
                new_object = self._hierarchy_viewmodel._scene_viewmodel.create_geometry(
                    geo_type=GeometryType.SPHERE, parent=parent_geometry)
            elif action == create_cylinder_action:
                # 创建圆柱体
                new_object = self._hierarchy_viewmodel._scene_viewmodel.create_geometry(
                    geo_type=GeometryType.CYLINDER, parent=parent_geometry)
        
        # 如果创建了新对象，更新树并选中新对象
        if new_object:
            # 更新树视图并选择新创建的对象
            self._update_tree()
            # 找到并选中新创建的对象
            self._select_geometry_by_id(id(new_object))
        
        # 处理其他菜单项（只有在选中项目时才有效）
        if item is not None:
            if action == rename_action:
                self.editItem(item)
            elif action == delete_action:
                # 获取对象并删除
                geometry_id = item.data(0, Qt.UserRole)
                for geometry in self._find_all_geometries(self._hierarchy_viewmodel.geometries):
                    if id(geometry) == geometry_id:
                        self._hierarchy_viewmodel._scene_viewmodel.remove_geometry(geometry)
                        break
            elif action == copy_action:
                # 获取对象并复制
                geometry_id = item.data(0, Qt.UserRole)
                for geometry in self._find_all_geometries(self._hierarchy_viewmodel.geometries):
                    if id(geometry) == geometry_id:
                        self._hierarchy_viewmodel.copy_geometry(geometry)
                        break
    
    def _select_geometry_by_id(self, geometry_id):
        """
        根据几何体ID在树中选择对应项
        
        参数:
            geometry_id: 几何体的ID
        """
        # 在所有顶层项中查找
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            # 检查当前项
            if item.data(0, Qt.UserRole) == geometry_id:
                self.setCurrentItem(item)
                return True
            # 递归检查子项
            if self._select_geometry_in_children(item, geometry_id):
                return True
        
        return False
    
    def _select_geometry_in_children(self, parent_item, geometry_id):
        """
        在父项的子项中递归查找并选择几何体
        
        参数:
            parent_item: 父树项
            geometry_id: 几何体的ID
            
        返回:
            bool: 是否找到并选中
        """
        for i in range(parent_item.childCount()):
            child_item = parent_item.child(i)
            # 检查当前子项
            if child_item.data(0, Qt.UserRole) == geometry_id:
                self.setCurrentItem(child_item)
                return True
            # 递归检查其子项
            if self._select_geometry_in_children(child_item, geometry_id):
                return True
        
        return False 