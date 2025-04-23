"""
层级树视图模型

处理场景对象层级结构
"""

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
import copy
from ..viewmodel.scene_viewmodel import SceneViewModel
class HierarchyViewModel(QObject):
    """
    层级树视图模型类
    
    处理场景对象的层级结构管理
    """
    # 信号
    hierarchyChanged = pyqtSignal()  # 层级结构发生变化
    selectionRequested = pyqtSignal(object)  # 请求选择指定对象
    
    def __init__(self, scene_viewmodel:SceneViewModel):
        """
        初始化层级树视图模型
        
        参数:
            scene_viewmodel: 场景视图模型的引用
        """
        super().__init__()
        self._scene_viewmodel = scene_viewmodel
        self._clipboard = None  # 用于复制粘贴的临时存储
        
        # 连接场景模型的信号
        self._scene_viewmodel.geometriesChanged.connect(self.on_geometries_changed)
    
    @property
    def geometries(self):
        """获取场景中的所有几何体"""
        return self._scene_viewmodel.geometries
    
    @property
    def selected_geometry(self):
        """获取当前选中的几何体"""
        return self._scene_viewmodel.selected_geometry
    
    def on_geometries_changed(self):
        """处理场景几何体变化"""
        self.hierarchyChanged.emit()
    
    def select_geometry(self, geometry):
        """
        选择指定几何体
        
        参数:
            geometry: 要选择的几何体
        """
        self._scene_viewmodel.selected_geometry = geometry
    
    def get_geometry_path(self, geometry):
        """
        获取几何体在层级中的路径
        
        参数:
            geometry: 目标几何体
            
        返回:
            list: 从根节点到目标几何体的路径
        """
        if not geometry:
            return []
        
        path = []
        current = geometry
        
        # 向上遍历父节点
        while current:
            path.insert(0, current)
            current = current.parent
        
        return path
    
    def create_group(self, name=None, parent=None):
        """
        创建新的组
        
        参数:
            name: 组名称（可选）
            parent: 父节点（可选）
            
        返回:
            创建的组对象
        """
        return self._scene_viewmodel.create_group(name, parent=parent)
    
    def remove_geometry(self, geometry):
        """
        删除几何体
        
        参数:
            geometry: 要删除的几何体
        """
        self._scene_viewmodel.remove_geometry(geometry)
    
    def copy_geometry(self, geometry):
        """
        复制几何体
        
        参数:
            geometry: 要复制的几何体
            
        返回:
            bool: 是否成功复制
        """
        if not geometry:
            return False
        
        # 深拷贝几何体（不包括父对象和子对象引用）
        self._clipboard = copy.deepcopy(geometry)
        
        # 清除父对象和子对象引用
        self._clipboard.parent = None
        self._clipboard.children = []
        
        return True
    
    def paste_geometry(self, parent=None):
        """
        粘贴之前复制的几何体
        
        参数:
            parent: 目标父节点（可选）
            
        返回:
            粘贴的几何体对象，如果剪贴板为空则返回None
        """
        if not self._clipboard:
            return None
        
        # 创建新的几何体实例
        if self._clipboard.type == 'group':
            # 如果是组，创建新的组
            new_geo = self._scene_viewmodel.create_group(
                name=f"{self._clipboard.name}_copy",
                position=self._clipboard.position,
                rotation=self._clipboard.rotation,
                parent=parent
            )
        else:
            # 如果是普通几何体，创建新的几何体
            new_geo = self._scene_viewmodel.create_geometry(
                geo_type=self._clipboard.type,
                name=f"{self._clipboard.name}_copy",
                position=self._clipboard.position,
                size=self._clipboard.size,
                rotation=self._clipboard.rotation,
                parent=parent
            )
            
            # 复制材质
            if hasattr(self._clipboard, 'material') and hasattr(new_geo, 'material'):
                new_geo.material.color = self._clipboard.material.color
        
        # 如果原始对象是组，且有子对象，我们需要递归复制
        if hasattr(self._clipboard, 'children') and self._clipboard.children:
            self._copy_children_recursive(self._clipboard, new_geo)
        
        # 选择新创建的几何体
        self._scene_viewmodel.selected_geometry = new_geo
        
        return new_geo
    
    def _copy_children_recursive(self, source, target):
        """
        递归复制子对象
        
        参数:
            source: 源对象
            target: 目标对象
        """
        if not hasattr(source, 'children') or not source.children:
            return
        
        for child in source.children:
            if child.type == 'group':
                # 复制组
                new_child = self._scene_viewmodel.create_group(
                    name=f"{child.name}_copy",
                    position=child.position,
                    rotation=child.rotation,
                    parent=target
                )
            else:
                # 复制几何体
                new_child = self._scene_viewmodel.create_geometry(
                    geo_type=child.type,
                    name=f"{child.name}_copy",
                    position=child.position,
                    size=child.size,
                    rotation=child.rotation,
                    parent=target
                )
                
                # 复制材质
                if hasattr(child, 'material') and hasattr(new_child, 'material'):
                    new_child.material.color = child.material.color
            
            # 递归复制子对象
            if hasattr(child, 'children') and child.children:
                self._copy_children_recursive(child, new_child)
    
    def reparent_geometry(self, geometry, new_parent):
        """
        重新设置几何体的父节点
        
        参数:
            geometry: 要移动的几何体
            new_parent: 新的父节点，如果为None则移动到顶层
            
        返回:
            bool: 是否成功移动
        """
        if not geometry:
            return False
        
        # 检查是否会形成循环引用
        if new_parent:
            current = new_parent
            while current:
                if current == geometry:
                    return False  # 检测到循环引用
                current = current.parent
        
        # 从原父节点移除
        if geometry.parent:
            old_parent = geometry.parent
            old_parent.remove_child(geometry)
        elif geometry in self._scene_viewmodel.geometries:
            self._scene_viewmodel.geometries.remove(geometry)
        
        # 添加到新父节点
        if new_parent:
            new_parent.add_child(geometry)
        else:
            self._scene_viewmodel.geometries.append(geometry)
            geometry.parent = None
        
        # 更新变换矩阵
        geometry.update_transform_matrix()
        
        # 触发更新
        self._scene_viewmodel.geometriesChanged.emit()
        
        return True 