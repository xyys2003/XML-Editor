"""
层级树视图

显示场景中对象的层级结构，允许用户选择和管理对象。
"""

from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu
from PyQt5.QtCore import Qt, pyqtSignal

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
        if item is None:
            return
        
        # 创建上下文菜单
        menu = QMenu(self)
        
        # 添加菜单项
        rename_action = menu.addAction("重命名")
        delete_action = menu.addAction("删除")
        menu.addSeparator()
        copy_action = menu.addAction("复制")
        
        # 显示菜单并处理结果
        action = menu.exec_(self.mapToGlobal(position))
        
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