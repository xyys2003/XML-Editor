"""
场景视图模型

作为场景数据和视图之间的桥梁，处理场景操作的业务逻辑
"""

from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np
import os

from ..model.geometry import (
    Geometry, GeometryGroup, GeometryType, 
    Material, OperationMode
)
from ..model.xml_parser import XMLParser
from ..model.raycaster import GeometryRaycaster, RaycastResult

class SceneViewModel(QObject):
    """
    场景视图模型类
    
    处理场景数据的加载、修改、保存，并通知视图更新
    """
    # 信号定义
    geometriesChanged = pyqtSignal()  # 几何体列表发生变化
    selectionChanged = pyqtSignal(object)  # 选中对象变化
    operationModeChanged = pyqtSignal(object)  # 操作模式变化
    objectChanged = pyqtSignal(object)  # 对象属性变化
    
    def __init__(self):
        super().__init__()
        self._geometries = []  # 场景中的几何体列表
        self._selected_geo = None  # 当前选中的几何体
        self._operation_mode = OperationMode.OBSERVE  # 当前操作模式
        self._raycaster = None  # 射线投射器
        self._camera_config = {
            'position': np.array([0, 0, 10]),
            'target': np.array([0, 0, 0]),
            'up': np.array([0, 1, 0]),
            'view_matrix': np.eye(4),
            'projection_matrix': np.eye(4)
        }
    
    @property
    def geometries(self):
        """获取所有几何体"""
        return self._geometries
    
    @geometries.setter
    def geometries(self, value):
        """设置几何体列表并发出通知"""
        self._geometries = value
        self._update_raycaster()
        self.geometriesChanged.emit()
    
    @property
    def selected_geometry(self):
        """获取当前选中的几何体"""
        return self._selected_geo
    
    @selected_geometry.setter
    def selected_geometry(self, value):
        """设置选中的几何体并发出通知"""
        # 先取消之前选中的几何体
        if self._selected_geo:
            self._selected_geo.selected = False
        
        self._selected_geo = value
        
        # 标记新选中的几何体
        if self._selected_geo:
            self._selected_geo.selected = True
        
        # 发出信号
        self.selectionChanged.emit(self._selected_geo)
    
    @property
    def transform_mode(self):
        """获取当前变换模式"""
        return self._operation_mode
    
    @transform_mode.setter
    def transform_mode(self, value):
        """设置变换模式并发出通知"""
        self._operation_mode = value
        self.operationModeChanged.emit(value)
    
    @property
    def operation_mode(self):
        """获取当前操作模式"""
        return self._operation_mode
    
    @operation_mode.setter
    def operation_mode(self, value):
        """设置操作模式并发出变换模式变化通知"""
        old_value = self._operation_mode
        self._operation_mode = value
        # 如果操作模式变化，也发出变换模式变化信号
        if old_value != value:
            self.operationModeChanged.emit(value)
    
    def set_camera_config(self, config):
        """设置摄像机配置"""
        self._camera_config.update(config)
        self._update_raycaster()
    
    def _update_raycaster(self):
        """更新射线投射器"""
        if self._raycaster:
            self._raycaster.update_camera(self._camera_config)
            self._raycaster.update_geometries(self._geometries)
        else:
            self._raycaster = GeometryRaycaster(self._camera_config, self._geometries)
    
    def create_geometry(self, geo_type, name=None, position=(0, 0, 0), size=(1, 1, 1), rotation=(0, 0, 0), parent=None):
        """
        创建新的几何体
        
        参数:
            geo_type: 几何体类型
            name: 几何体名称（如果为None则自动生成）
            position: 位置坐标
            size: 尺寸
            rotation: 旋转角度
            parent: 父对象
        
        返回:
            创建的几何体对象
        """
        # 自动生成名称
        if name is None:
            counter = sum(1 for g in self.get_all_geometries() if g.type == geo_type.value)
            type_name = geo_type.name.capitalize()
            name = f"{type_name}{counter + 1}"
        
        # 创建几何体
        geometry = Geometry(
            geo_type=geo_type.value,
            name=name,
            position=position,
            size=size,
            rotation=rotation,
            parent=parent
        )
        
        # 添加到场景中
        if parent:
            parent.add_child(geometry)
        else:
            self._geometries.append(geometry)
        
        # 触发更新
        self.geometriesChanged.emit()
        
        return geometry
    
    def create_group(self, name=None, position=(0, 0, 0), rotation=(0, 0, 0), parent=None):
        """
        创建新的几何体组
        
        参数:
            name: 组名称（如果为None则自动生成）
            position: 位置坐标
            rotation: 旋转角度
            parent: 父对象
        
        返回:
            创建的几何体组对象
        """
        # 自动生成名称
        if name is None:
            counter = sum(1 for g in self.get_all_geometries() if hasattr(g, 'type') and g.type == 'group')
            name = f"Group{counter + 1}"
        
        # 创建几何体组
        group = GeometryGroup(
            name=name,
            position=position,
            rotation=rotation,
            parent=parent
        )
        
        # 添加到场景中
        if parent:
            parent.add_child(group)
        else:
            self._geometries.append(group)
        
        # 触发更新
        self.geometriesChanged.emit()
        
        return group
    
    def remove_geometry(self, geometry):
        """
        从场景中移除几何体
        
        参数:
            geometry: 要移除的几何体
        """
        # 如果是当前选中的几何体，先取消选中
        if self._selected_geo == geometry:
            self.selected_geometry = None
        
        # 从父对象中移除
        if geometry.parent:
            geometry.parent.remove_child(geometry)
        # 从顶层列表中移除
        elif geometry in self._geometries:
            self._geometries.remove(geometry)
        
        # 触发更新
        self.geometriesChanged.emit()
    
    def select_at(self, screen_x, screen_y, viewport_width, viewport_height):
        """
        在指定屏幕坐标选择几何体
        
        参数:
            screen_x: 屏幕X坐标
            screen_y: 屏幕Y坐标
            viewport_width: 视口宽度
            viewport_height: 视口高度
        
        返回:
            bool: 是否选中了几何体
        """
        result = self._raycaster.raycast(screen_x, screen_y, viewport_width, viewport_height)

        if result.is_hit():
            self.selected_geometry = result.geometry
            return True
        else:
            return False
    
    def clear_selection(self):
        """清除当前选择"""
        self.selected_geometry = None
    
    def load_scene(self, filename):
        """
        从文件加载场景
        
        参数:
            filename: 要加载的文件路径
            
        返回:
            bool: 是否成功加载
        """
        try:
            self._geometries = XMLParser.load(filename)
            self._update_raycaster()
            self.geometriesChanged.emit()
            return True
        except Exception as e:
            print(f"加载场景失败: {e}")
            return False
    
    def save_scene(self, filename):
        """
        保存场景到文件
        
        参数:
            filename: 保存的文件路径
            
        返回:
            bool: 是否成功保存
        """
        try:
            # 根据文件扩展名决定保存格式
            _, ext = os.path.splitext(filename)
            
            if ext.lower() == '.xml':
                return XMLParser.export_mujoco_xml(filename, self._geometries)
            else:
                return XMLParser.export_enhanced_xml(filename, self._geometries)
        except Exception as e:
            print(f"保存场景失败: {e}")
            return False
    
    def get_all_geometries(self):
        """
        获取场景中的所有几何体（包括嵌套在组中的）
        
        返回:
            list: 所有几何体的列表
        """
        result = []
        
        for geo in self._geometries:
            result.append(geo)
            if hasattr(geo, 'children') and geo.children:
                result.extend(self._get_children_recursive(geo))
        
        return result
    
    def _get_children_recursive(self, parent):
        """递归获取所有子对象"""
        result = []
        
        for child in parent.children:
            result.append(child)
            if hasattr(child, 'children') and child.children:
                result.extend(self._get_children_recursive(child))
        
        return result
    
    def update_geometry_property(self, geometry, property_name, value):
        """
        更新几何体的属性
        
        参数:
            geometry: 要更新的几何体
            property_name: 属性名称
            value: 新的属性值
            
        返回:
            bool: 是否成功更新
        """
        if not geometry:
            return False
        
        try:
            if property_name == 'name':
                geometry.name = value
            elif property_name == 'position':
                geometry.position = value
            elif property_name == 'size':
                geometry.size = value
            elif property_name == 'rotation':
                geometry.rotation = value
            elif property_name == 'color':
                geometry.material.color = value
            else:
                return False
                
            # 如果更新了变换相关属性，更新变换矩阵
            if property_name in ('position', 'size', 'rotation'):
                geometry.update_transform_matrix()
                
                # 递归更新所有子对象的变换矩阵
                if hasattr(geometry, 'children') and geometry.children:
                    for child in geometry.children:
                        self._update_transform_recursive(child)
            
            # 触发更新
            self.geometriesChanged.emit()
                
            return True
        except Exception as e:
            print(f"更新几何体属性失败: {e}")
            return False
    
    def _update_transform_recursive(self, geometry):
        """递归更新几何体及其子对象的变换矩阵"""
        if hasattr(geometry, 'update_transform_matrix'):
            geometry.update_transform_matrix()
        
        if hasattr(geometry, 'children') and geometry.children:
            for child in geometry.children:
                self._update_transform_recursive(child)
    
    def notify_object_changed(self, obj):
        """
        通知对象已更改
        
        参数:
            obj: 被修改的对象
        """
        # 发出对象变化信号
        self.objectChanged.emit(obj)
        
        # 同时发出几何体列表变化信号，更新视图
        self.geometriesChanged.emit()
    
    def screen_to_world_ray(self, screen_x, screen_y, viewport_width, viewport_height):
        """
        从屏幕坐标计算世界空间射线
        
        参数:
            screen_x, screen_y: 屏幕坐标
            viewport_width, viewport_height: 视口尺寸
            
        返回:
            (ray_origin, ray_direction): 射线起点和方向
        """
        # 转换为归一化设备坐标(NDC)
        ndc_x = (2.0 * screen_x / viewport_width) - 1.0
        ndc_y = 1.0 - (2.0 * screen_y / viewport_height)  # Y轴方向翻转
        
        # 获取近平面和远平面上的点
        near_point = self.unproject_point(ndc_x, ndc_y, 0.0)
        far_point = self.unproject_point(ndc_x, ndc_y, 1.0)
        
        # 射线起点(相机位置)
        ray_origin = np.array(self._camera_config['position'])
        
        # 射线方向
        ray_direction = np.array(far_point) - np.array(near_point)
        ray_direction = ray_direction / np.linalg.norm(ray_direction)  # 归一化
        
        return (ray_origin, ray_direction)
    
    def unproject_point(self, ndc_x, ndc_y, ndc_z):
        """
        将归一化设备坐标转换为世界坐标
        
        参数:
            ndc_x, ndc_y, ndc_z: 归一化设备坐标(范围[-1,1])
            
        返回:
            世界坐标(x, y, z)
        """
        # 获取投影和视图矩阵
        proj_matrix = self._camera_config['projection_matrix']
        view_matrix = self._camera_config['view_matrix']
        
        # 计算视图投影矩阵的逆矩阵
        view_proj = np.matmul(proj_matrix, view_matrix)
        inv_view_proj = np.linalg.inv(view_proj)
        
        # 将NDC坐标转换为齐次裁剪空间坐标
        clip_coords = np.array([ndc_x, ndc_y, ndc_z, 1.0])
        
        # 应用逆矩阵转换为世界坐标
        world_coords = np.matmul(inv_view_proj, clip_coords)
        
        # 透视除法
        if world_coords[3] != 0:
            world_coords = world_coords / world_coords[3]
        
        return world_coords[:3] 