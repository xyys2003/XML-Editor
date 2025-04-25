"""
层级树视图模型

处理场景对象层级结构
"""

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
import copy
from ..viewmodel.scene_viewmodel import SceneViewModel
from ..model.geometry import GeometryType

class HierarchyViewModel(QObject):
    """
    层级树视图模型类
    
    处理场景对象的层级结构管理
    """
    # 信号
    hierarchyChanged = pyqtSignal()  # 层级结构发生变化
    selectionChanged = pyqtSignal(list)  # 选择改变，参数为选中的几何体列表
    
    def __init__(self, scene_viewmodel:SceneViewModel):
        """
        初始化层级树视图模型
        
        参数:
            scene_viewmodel: 场景视图模型的引用
        """
        super().__init__()
        self._scene_viewmodel = scene_viewmodel
        self._clipboard_items = []  # 用于复制粘贴的临时存储，列表形式
        self._selected_geometries = []  # 当前选中的几何体列表
        
        # 连接场景模型的信号
        self._scene_viewmodel.geometriesChanged.connect(self.on_geometries_changed)
    
    @property
    def geometries(self):
        """获取场景中的所有几何体"""
        return self._scene_viewmodel.geometries
    
    @property
    def selected_geometries(self):
        """获取当前选中的几何体列表"""
        return self._selected_geometries
    
    @property
    def selected_geometry(self):
        """获取主选中几何体（向后兼容）"""
        return self._scene_viewmodel.selected_geometry
    
    @property
    def has_clipboard_content(self):
        """检查剪贴板是否有内容"""
        return len(self._clipboard_items) > 0
    
    def on_geometries_changed(self):
        """处理场景几何体变化"""
        # 清理已删除的几何体
        self._selected_geometries = [g for g in self._selected_geometries 
                                     if g in self._find_all_geometries(self.geometries)]
        # 发送信号
        self.hierarchyChanged.emit()
        self.selectionChanged.emit(self._selected_geometries)
    
    def select_geometry(self, geometry):
        """
        选择单个几何体（向后兼容）
        
        参数:
            geometry: 要选择的几何体
        """
        self._selected_geometries = [geometry] if geometry else []
        self._scene_viewmodel.selected_geometry = geometry
        self.selectionChanged.emit(self._selected_geometries)
    
    def select_geometries(self, geometries):
        """
        选择多个几何体
        
        参数:
            geometries: 要选择的几何体列表
        """
        self._selected_geometries = list(geometries) if geometries else []
        
        # 更新主选中对象（为兼容性）
        if self._selected_geometries:
            self._scene_viewmodel.selected_geometry = self._selected_geometries[-1]
        else:
            self._scene_viewmodel.selected_geometry = None
            
        self.selectionChanged.emit(self._selected_geometries)
    
    def toggle_geometry_selection(self, geometry):
        """
        切换几何体的选择状态
        
        参数:
            geometry: 要切换的几何体
        """
        if geometry in self._selected_geometries:
            self._selected_geometries.remove(geometry)
        else:
            self._selected_geometries.append(geometry)
            
        # 更新主选中对象
        if self._selected_geometries:
            self._scene_viewmodel.selected_geometry = self._selected_geometries[-1]
        else:
            self._scene_viewmodel.selected_geometry = None
            
        self.selectionChanged.emit(self._selected_geometries)
    
    def clear_selection(self):
        """清空选择"""
        self._selected_geometries = []
        self._scene_viewmodel.selected_geometry = None
        self.selectionChanged.emit(self._selected_geometries)
    
    def copy_selected_geometries(self):
        """
        复制选中的几何体
        
        返回:
            bool: 是否成功复制
        """
        if not self._selected_geometries:
            return False
        
        # 清空剪贴板
        self._clipboard_items = []
        
        # 复制所有选中的几何体
        for geometry in self._selected_geometries:
            # 深拷贝几何体
            copied = copy.deepcopy(geometry)
            
            # 清除父对象引用
            copied.parent = None
            
            # 更新所有子对象的父引用
            self._update_parent_references(copied)
            
            # 添加到剪贴板
            self._clipboard_items.append(copied)
        
        return True
    
    def _update_parent_references(self, geometry):
        """
        更新几何体子对象的父引用
        
        参数:
            geometry: 要更新的几何体
        """
        if not hasattr(geometry, 'children'):
            return
        
        for child in geometry.children:
            child.parent = geometry
            if hasattr(child, 'children') and child.children:
                self._update_parent_references(child)
    
    def paste_geometries(self, parent=None):
        """
        粘贴复制的几何体
        
        参数:
            parent: 目标父节点（可选）
            
        返回:
            list: 粘贴的几何体对象列表
        """
        if not self._clipboard_items:
            return []
        
        new_objects = []
        
        # 创建每个复制的几何体
        for item in self._clipboard_items:
            if item.type == 'group':
                # 复制组
                new_geo = self._scene_viewmodel.create_group(
                    name=f"{item.name}_copy",
                    position=item.position,
                    rotation=item.rotation,
                    parent=parent
                )
            else:
                # 复制几何体
                # 将字符串类型转换为GeometryType枚举
                geo_type_map = {
                    'box': GeometryType.BOX,
                    'sphere': GeometryType.SPHERE,
                    'cylinder': GeometryType.CYLINDER,
                    'capsule': GeometryType.CAPSULE,
                    'plane': GeometryType.PLANE,
                    'ellipsoid': GeometryType.ELLIPSOID,
                    'triangle': GeometryType.TRIANGLE
                }
                geo_type = geo_type_map.get(item.type)
                
                if geo_type is None:
                    print(f"未知的几何体类型: {item.type}")
                    continue
                
                new_geo = self._scene_viewmodel.create_geometry(
                    geo_type=geo_type,
                    name=f"{item.name}_copy",
                    position=item.position,
                    size=item.size,
                    rotation=item.rotation,
                    parent=parent
                )
                
                # 复制材质
                if hasattr(item, 'material') and hasattr(new_geo, 'material'):
                    new_geo.material.color = item.material.color
            
            # 递归复制子对象
            if hasattr(item, 'children') and item.children:
                self._copy_children_recursive(item, new_geo)
            
            new_objects.append(new_geo)
        
        # 选择新创建的几何体
        if new_objects:
            self.select_geometries(new_objects)
        
        return new_objects
    
    def _copy_children_recursive(self, source, target):
        """
        递归复制子对象
        
        参数:
            source: 源对象
            target: 目标对象
        """
        if not hasattr(source, 'children') or not source.children:
            return
        
        # 映射字符串类型到GeometryType枚举
        geo_type_map = {
            'box': GeometryType.BOX,
            'sphere': GeometryType.SPHERE,
            'cylinder': GeometryType.CYLINDER,
            'capsule': GeometryType.CAPSULE,
            'plane': GeometryType.PLANE,
            'ellipsoid': GeometryType.ELLIPSOID,
            'triangle': GeometryType.TRIANGLE
        }
        
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
                # 获取枚举类型
                geo_type = geo_type_map.get(child.type)
                
                if geo_type is None:
                    print(f"未知的几何体类型: {child.type}")
                    continue
                    
                # 复制几何体
                new_child = self._scene_viewmodel.create_geometry(
                    geo_type=geo_type,
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
    
    def remove_selected_geometries(self):
        """
        删除所有选中的几何体
        
        返回:
            bool: 是否有几何体被删除
        """
        if not self._selected_geometries:
            return False
        
        # 复制列表以避免在迭代过程中修改
        geometries_to_remove = list(self._selected_geometries)
        self.clear_selection()
        
        # 删除每个几何体
        for geometry in geometries_to_remove:
            self._scene_viewmodel.remove_geometry(geometry)
        
        return True
    
    def group_selected_geometries(self):
        """
        将选中的几何体组合到一个新的组中
        
        返回:
            新创建的组对象，如果没有足够的选中项则返回None
        """
        if len(self._selected_geometries) < 2:
            return None
        
        # 获取第一个对象的父节点作为新组的父节点
        parent = self._selected_geometries[0].parent
        
        # 创建新组
        new_group = self._scene_viewmodel.create_group(name="New Group", parent=parent)
        
        # 将所有选中的几何体移动到新组中
        for geometry in self._selected_geometries:
            self.reparent_geometry(geometry, new_group)
        
        # 选择新创建的组
        self.select_geometry(new_group)
        
        return new_group
    
    def _find_all_geometries(self, geometries):
        """
        递归查找所有几何体
        
        参数:
            geometries: 几何体列表
            
        返回:
            所有几何体的平面列表
        """
        result = []
        for geometry in geometries:
            result.append(geometry)
            if hasattr(geometry, 'children') and geometry.children:
                result.extend(self._find_all_geometries(geometry.children))
        return result
    
    # 向后兼容的方法
    def copy_geometry(self, geometry):
        """单个几何体复制（向后兼容）"""
        self.select_geometry(geometry)
        return self.copy_selected_geometries()
    
    def paste_geometry(self, parent=None):
        """单个几何体粘贴（向后兼容）"""
        new_objects = self.paste_geometries(parent)
        return new_objects[0] if new_objects else None
    
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
        new_group = self._scene_viewmodel.create_group(name, parent=parent)
        
        # 触发更新
        self._scene_viewmodel.geometriesChanged.emit()
        
        # 自动选择新创建的组
        self.select_geometry(new_group)
        
        return new_group
    
    def remove_geometry(self, geometry):
        """
        删除几何体
        
        参数:
            geometry: 要删除的几何体
        """
        self._scene_viewmodel.remove_geometry(geometry)
    
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
        
        # 自动选择被操作的几何体
        self.select_geometry(geometry)
        
        return True
    
    def group_geometries(self, geometries, name="New Group", parent=None):
        """
        将多个几何体组合到一个新组中
        
        参数:
            geometries: 要组合的几何体列表
            name: 新组名称（可选）
            parent: 新组的父节点（可选）
        
        返回:
            新创建的组对象
        """
        if not geometries or len(geometries) < 2:
            return None
        
        # 创建新组
        new_group = self._scene_viewmodel.create_group(name=name, parent=parent)
        
        # 将所有几何体移动到新组中
        for geometry in geometries:
            self.reparent_geometry(geometry, new_group)
        
        # 选择新创建的组
        self.select_geometry(new_group)
        
        # 触发更新
        self._scene_viewmodel.geometriesChanged.emit()
        
        return new_group 